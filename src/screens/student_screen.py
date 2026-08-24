import streamlit as st
from src.ui.base_layout import style_background_dashboard, style_base_layout
from src.components.header import header_dashboard
from src.components.footer import footer_dashboard
from PIL import Image
import numpy as np
from src.pipelines.face_pipeline import predict_attendance, get_face_embeddings, train_classifier
from src.pipelines.voice_pipeline import get_voice_embedding
from src.database.db import get_all_students, create_student, get_student_subjects, get_student_attendance, unenroll_student_to_subject
import time
from src.components.dialog_enroll import enroll_dialog
from src.components.subject_card import subject_card

def student_dashboard():
    student_data = st.session_state.student_data
    student_id = student_data['student_id']

    c1, c2 = st.columns([2, 1], vertical_alignment='center')
    with c1:
        header_dashboard()
    with c2:
        st.markdown(f"<div style='text-align: right;'><span style='color: #64748B; font-size: 0.9rem;'>Logged in as:</span><br/><strong style='font-size: 1.15rem; color: #0F172A;'>{student_data['name']}</strong></div>", unsafe_allow_html=True)
        if st.button("Log Out", type='secondary', key='logout_student_btn', icon=':material/logout:'):
            st.session_state['is_logged_in'] = False
            if 'student_data' in st.session_state:
                del st.session_state.student_data
            st.rerun()

    st.divider()

    # Load data
    with st.spinner('Loading enrolled courses & attendance records...'):
        subjects = get_student_subjects(student_id) or []
        logs = get_student_attendance(student_id) or []

    stats_map = {}
    total_attended_overall = 0
    total_sessions_overall = len(logs)

    for log in logs:
        sid = log['subject_id']
        if sid not in stats_map:
            stats_map[sid] = {"total": 0, "attended": 0}

        stats_map[sid]['total'] += 1
        if log.get('is_present'):
            stats_map[sid]['attended'] += 1
            total_attended_overall += 1

    overall_pct = int((total_attended_overall / total_sessions_overall * 100)) if total_sessions_overall > 0 else 0

    # Analytics Metrics Row
    m1, m2, m3 = st.columns(3)
    with m1:
        st.markdown(f"""
        <div class="metric-card">
            <span class="label">Enrolled Subjects</span>
            <span class="value">{len(subjects)}</span>
        </div>
        """, unsafe_allow_html=True)
    with m2:
        st.markdown(f"""
        <div class="metric-card">
            <span class="label">Classes Attended</span>
            <span class="value">{total_attended_overall} <span style="font-size: 1rem; color: #64748B; font-weight: 500;">/ {total_sessions_overall}</span></span>
        </div>
        """, unsafe_allow_html=True)
    with m3:
        color = "#16A34A" if overall_pct >= 75 else ("#CA8A04" if overall_pct >= 50 else "#DC2626")
        st.markdown(f"""
        <div class="metric-card">
            <span class="label">Overall Attendance</span>
            <span class="value" style="color: {color};">{overall_pct}%</span>
        </div>
        """, unsafe_allow_html=True)

    st.write("")
    st.write("")

    # Enrolled Subjects Section
    c1, c2 = st.columns([2, 1], vertical_alignment='center')
    with c1:
        st.subheader('Enrolled Subjects')
    with c2:
        if st.button('Enroll in New Subject', type='primary', width='stretch', icon=':material/add:'):
            enroll_dialog()

    if not subjects:
        st.info("You haven't enrolled in any subjects yet. Click **Enroll in New Subject** or scan a teacher's QR code.")
    else:
        cols = st.columns(2, gap="medium")
        for i, sub_node in enumerate(subjects):
            sub = sub_node['subjects']
            sid = sub['subject_id']
            stats = stats_map.get(sid, {"total": 0, "attended": 0})
            sub_pct = int((stats['attended'] / stats['total'] * 100)) if stats['total'] > 0 else 0

            def make_unenroll(current_sid=sid, current_sub_name=sub['name']):
                def unenroll_button():
                    if st.button(f"Unenroll", key=f"unenroll_{current_sid}", type='secondary', icon=':material/delete:'):
                        unenroll_student_to_subject(student_id, current_sid)
                        st.toast(f'Unenrolled from {current_sub_name} successfully!')
                        time.sleep(0.5)
                        st.rerun()
                return unenroll_button

            with cols[i % 2]:
                subject_card(
                    name=sub['name'],
                    code=sub['subject_code'],
                    section=sub['section'],
                    stats=[
                        ('📅', 'Total Sessions', stats['total']),
                        ('✅', 'Attended', stats['attended']),
                        ('📊', 'Rate', f"{sub_pct}%")
                    ],
                    footer_callback=make_unenroll(sid, sub['name'])
                )

    footer_dashboard()


def student_screen():
    style_background_dashboard()
    style_base_layout()

    if "student_data" in st.session_state:
        student_dashboard()
        return

    c1, c2 = st.columns([3, 1], vertical_alignment='center')
    with c1:
        header_dashboard()
    with c2:
        if st.button("Back to Home", type='secondary', key='student_home_btn', icon=':material/arrow_back:'):
            st.session_state['login_type'] = None
            st.rerun()

    st.write("")
    st.markdown("<h2 style='text-align: center;'>Student Biometric Portal</h2>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: #64748B;'>Look directly into the camera to authenticate via <strong>FaceID</strong> or create your profile.</p>", unsafe_allow_html=True)

    col_cam, col_info = st.columns([1.2, 1], gap="large")

    with col_cam:
        photo_source = st.camera_input("Position your face in the frame", key="student_face_cam")

    show_registration = False

    with col_info:
        if not photo_source:
            st.markdown("""
            <div style="background: white; border-radius: 1.25rem; border: 1px solid #E2E8F0; padding: 1.5rem; margin-top: 1rem;">
                <h4 style="margin: 0 0 0.5rem 0; color: #4F46E5;">📸 Quick Authentication Tips</h4>
                <ul style="color: #64748B; font-size: 0.9rem; padding-left: 1.25rem; line-height: 1.6;">
                    <li>Ensure good lighting on your face.</li>
                    <li>Avoid heavy shadows, sunglasses, or face coverings.</li>
                    <li>If you are a new student, your profile will be registered automatically.</li>
                </ul>
            </div>
            """, unsafe_allow_html=True)
        else:
            img = np.array(Image.open(photo_source))

            with st.spinner('Running AI facial biometric scan...'):
                detected, all_ids, num_faces = predict_attendance(img)

                if num_faces == 0:
                    st.warning('⚠️ No face detected. Please center your face clearly in the camera viewfinder.')
                elif num_faces > 1:
                    st.warning('⚠️ Multiple faces detected! Please ensure only one student is in front of the camera.')
                else:
                    if detected:
                        student_id = list(detected.keys())[0]
                        all_students = get_all_students() or []
                        student = next((s for s in all_students if s['student_id'] == student_id), None)

                        if student:
                            st.success(f"🎉 Welcome back, **{student['name']}**!")
                            st.session_state.is_logged_in = True
                            st.session_state.user_role = 'student'
                            st.session_state.student_data = student
                            st.toast(f"Authenticated as {student['name']}", icon="✅")
                            time.sleep(0.8)
                            st.rerun()
                    else:
                        st.info("✨ Face not recognized. You appear to be a new student! Complete the profile registration below.")
                        show_registration = True

    if show_registration and photo_source:
        st.write("")
        st.markdown("---")
        st.subheader("📝 Register New Student Profile")
        
        with st.container():
            rc1, rc2 = st.columns([1, 1], gap="medium")
            with rc1:
                new_name = st.text_input("Full Name *", placeholder="e.g. Alex Morgan")
                st.caption("Your name as officially registered with the institution.")

            with rc2:
                st.markdown("**🎙️ Optional: Voice Biometric Enrollment**")
                st.caption("Record yourself saying: *'I am present, my name is [Your Name]'*")
                audio_data = None
                try:
                    audio_data = st.audio_input("Record Voice Sample", key="reg_voice_sample")
                except Exception:
                    st.caption("Audio input not supported on this browser.")

            st.write("")
            if st.button('Complete Profile & Enter Portal', type='primary', width='stretch', icon=':material/check_circle:'):
                if new_name.strip():
                    with st.spinner('Extracting facial descriptors & building profile...'):
                        img = np.array(Image.open(photo_source))
                        encodings = get_face_embeddings(img)
                        if encodings:
                            face_emb = encodings[0].tolist()
                            voice_emb = None
                            if audio_data:
                                try:
                                    voice_emb, voice_msg = safe_get_voice_embedding(audio_data.read())
                                    if voice_emb is None:
                                        st.warning(f"Voice sample skipped: {voice_msg} — continuing with FaceID registration.")
                                except Exception:
                                    st.warning("Could not process voice sample, registering with FaceID only.")

                            response_data = create_student(new_name.strip(), face_embedding=face_emb, voice_embedding=voice_emb)

                            if response_data:
                                train_classifier()
                                st.session_state.is_logged_in = True
                                st.session_state.user_role = 'student'
                                st.session_state.student_data = response_data[0]
                                st.success(f"Profile created! Welcome to SnapClass, {new_name}!")
                                time.sleep(1)
                                st.rerun()
                        else:
                            st.error('Could not capture facial landmarks properly. Please try capturing another photo.')
                else:
                    st.warning('Please provide your full name to complete registration.')

    footer_dashboard()