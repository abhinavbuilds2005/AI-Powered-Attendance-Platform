import streamlit as st
from src.ui.base_layout import style_background_dashboard, style_base_layout
from src.components.header import header_dashboard
from src.components.footer import footer_dashboard
from src.components.subject_card import subject_card
from src.database.db import check_teacher_exists, create_teacher, teacher_login, get_teacher_subjects, get_attendance_for_teacher
from src.components.dialog_create_subject import create_subject_dialog
from src.components.dialog_share_subject import share_subject_dialog
from src.components.dialog_add_photo import add_photos_dialog
from src.pipelines.face_pipeline import predict_attendance
from src.components.dialog_attendance_results import attendance_result_dialog
from src.components.dialog_voice_attendance import voice_attendance_dialog
import numpy as np
from datetime import datetime
import pandas as pd
from src.database.config import supabase
import time

def teacher_screen():
    style_background_dashboard()
    style_base_layout()

    if "teacher_data" in st.session_state:
        teacher_dashboard()
    elif 'teacher_login_type' not in st.session_state or st.session_state.teacher_login_type == "login":
        teacher_screen_login()
    elif st.session_state.teacher_login_type == "register":
        teacher_screen_register()


def teacher_dashboard():
    teacher_data = st.session_state.teacher_data

    c1, c2 = st.columns([2, 1], vertical_alignment='center')
    with c1:
        header_dashboard()
    with c2:
        st.markdown(f"<div style='text-align: right;'><span style='color: #64748B; font-size: 0.9rem;'>Instructor:</span><br/><strong style='font-size: 1.15rem; color: #0F172A;'>{teacher_data['name']}</strong></div>", unsafe_allow_html=True)
        if st.button("Log Out", type='secondary', key='logout_teacher_btn', icon=':material/logout:'):
            st.session_state['is_logged_in'] = False
            if 'teacher_data' in st.session_state:
                del st.session_state.teacher_data
            st.rerun()

    st.write("")

    if "current_teacher_tab" not in st.session_state:
        st.session_state.current_teacher_tab = 'take_attendance'

    # Navigation Tabs
    tab1, tab2, tab3 = st.columns(3, gap="small")

    with tab1:
        type1 = "primary" if st.session_state.current_teacher_tab == 'take_attendance' else "secondary"
        if st.button('📸 Take Attendance', type=type1, width='stretch'):
            st.session_state.current_teacher_tab = 'take_attendance'
            st.rerun()

    with tab2:
        type2 = "primary" if st.session_state.current_teacher_tab == 'manage_subjects' else "secondary"
        if st.button('📚 Manage Subjects', type=type2, width='stretch'):
            st.session_state.current_teacher_tab = 'manage_subjects'
            st.rerun()

    with tab3:
        type3 = "primary" if st.session_state.current_teacher_tab == 'attendance_records' else "secondary"
        if st.button('📊 Attendance Analytics', type=type3, width='stretch'):
            st.session_state.current_teacher_tab = 'attendance_records'
            st.rerun()

    st.divider()

    if st.session_state.current_teacher_tab == "take_attendance":
        teacher_tab_take_attendance()
    elif st.session_state.current_teacher_tab == "manage_subjects":
        teacher_tab_manage_subjects()
    elif st.session_state.current_teacher_tab == "attendance_records":
        teacher_tab_attendance_records()

    footer_dashboard()


def teacher_tab_take_attendance():
    teacher_id = st.session_state.teacher_data['teacher_id']
    
    st.subheader('Take Multimodal AI Attendance')
    st.caption('Upload classroom snapshots or use voice verification to automatically detect and mark present students.')

    if 'attendance_images' not in st.session_state:
        st.session_state.attendance_images = []

    subjects = get_teacher_subjects(teacher_id) or []

    if not subjects:
        st.warning('⚠️ You have not created any courses yet! Please go to **Manage Subjects** to create your first class.')
        return

    subject_options = {f"{s['name']} ({s['subject_code']}) - Sec {s['section']}": s['subject_id'] for s in subjects}

    col1, col2 = st.columns([3, 1], vertical_alignment='bottom')
    with col1:
        selected_subject_label = st.selectbox('Select Target Course', options=list(subject_options.keys()))

    with col2:
        if st.button('Add Photos', type='primary', icon=':material/add_photo_alternate:', width='stretch'):
            add_photos_dialog()

    selected_subject_id = subject_options[selected_subject_label]

    st.write("")

    # Photos Gallery
    if st.session_state.attendance_images:
        st.markdown(f"**Classroom Photos ({len(st.session_state.attendance_images)} attached)**")
        gallery_cols = st.columns(4, gap="medium")

        for idx, img in enumerate(st.session_state.attendance_images):
            with gallery_cols[idx % 4]:
                st.image(img, width='stretch', caption=f'Photo {idx+1}')

    has_photos = bool(st.session_state.attendance_images)
    
    c1, c2, c3 = st.columns(3, gap="medium")

    with c1:
        if st.button('Clear All Photos', width='stretch', type='secondary', icon=':material/delete_sweep:', disabled=not has_photos):
            st.session_state.attendance_images = []
            st.rerun()

    with c2:
        if st.button('Run Face Scan Analysis', width='stretch', type='primary', icon=':material/face_unlock:', disabled=not has_photos):
            with st.spinner('AI is performing deep facial scanning across all classroom photos...'):
                all_detected_ids = {}

                for idx, img in enumerate(st.session_state.attendance_images):
                    img_np = np.array(img.convert('RGB'))
                    detected, _, _ = predict_attendance(img_np)

                    if detected:
                        for sid in detected.keys():
                            student_id = int(sid)
                            all_detected_ids.setdefault(student_id, []).append(f"Photo {idx+1}")

                enrolled_res = supabase.table('subject_students').select("*, students(*)").eq('subject_id', selected_subject_id).execute()
                enrolled_students = enrolled_res.data or []

                if not enrolled_students:
                    st.warning('No students are currently enrolled in this course.')
                else:
                    results, attendance_to_log = [], []
                    current_timestamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

                    for node in enrolled_students:
                        student = node['students']
                        sources = all_detected_ids.get(int(student['student_id']), [])
                        is_present = len(sources) > 0

                        results.append({
                            "Name": student['name'],
                            "ID": student['student_id'],
                            "Source": ", ".join(sources) if is_present else "-",
                            "Status": "✅ Present" if is_present else "❌ Absent"
                        })

                        attendance_to_log.append({
                            'student_id': student['student_id'],
                            'subject_id': selected_subject_id,
                            'timestamp': current_timestamp,
                            'is_present': bool(is_present)
                        })

                    attendance_result_dialog(pd.DataFrame(results), attendance_to_log)

    with c3:
        if st.button('Use Voice Attendance', type='secondary', width='stretch', icon=':material/mic:'):
            voice_attendance_dialog(selected_subject_id)


def teacher_tab_manage_subjects():
    teacher_id = st.session_state.teacher_data['teacher_id']
    
    c1, c2 = st.columns([2, 1], vertical_alignment='center')
    with c1:
        st.subheader('Manage Courses & Subjects')
    with c2:
        if st.button('Create New Subject', type='primary', width='stretch', icon=':material/add:'):
            create_subject_dialog(teacher_id)

    st.write("")

    subjects = get_teacher_subjects(teacher_id) or []
    if subjects:
        cols = st.columns(2, gap="medium")
        for i, sub in enumerate(subjects):
            stats = [
                ("👥", "Enrolled Students", sub.get('total_students', 0)),
                ("🗓️", "Conducted Sessions", sub.get('total_classes', 0)),
            ]
            
            def make_share(sub_name=sub['name'], sub_code=sub['subject_code']):
                def share_btn():
                    if st.button(f"Share Code & QR", key=f"share_{sub_code}", icon=":material/qr_code_2:"):
                        share_subject_dialog(sub_name, sub_code)
                return share_btn

            with cols[i % 2]:
                subject_card(
                    name=sub['name'],
                    code=sub['subject_code'],
                    section=sub['section'],
                    stats=stats,
                    footer_callback=make_share(sub['name'], sub['subject_code'])
                )
    else:
        st.info("No courses found. Click **Create New Subject** above to get started.")


def teacher_tab_attendance_records():
    teacher_id = st.session_state.teacher_data['teacher_id']
    
    st.subheader('Attendance Records & Export')
    st.caption('Inspect historical attendance records across your classes and export data.')

    records = get_attendance_for_teacher(teacher_id) or []

    if not records:
        st.info("No attendance records found yet. Take attendance to see data here.")
        return

    data = []
    for r in records:
        ts = r.get('timestamp')
        data.append({
            "ts_group": ts.split(".")[0] if ts else None,
            "Date & Time": datetime.fromisoformat(ts).strftime("%Y-%m-%d %I:%M %p") if ts else "N/A",
            "Subject": r['subjects']['name'],
            "Subject Code": r['subjects']['subject_code'],
            "is_present": bool(r.get('is_present', False))
        })

    df = pd.DataFrame(data)

    # Aggregated Summary
    summary = (
        df.groupby(['ts_group', 'Date & Time', 'Subject', 'Subject Code'])
        .agg(
            Present_Count=('is_present', 'sum'),
            Total_Count=('is_present', 'count')
        ).reset_index()
    )

    summary['Attendance Rate'] = ((summary['Present_Count'] / summary['Total_Count']) * 100).round(1).astype(str) + "%"
    summary['Attendance Breakdown'] = (
        "✅ " + summary['Present_Count'].astype(str) + " / "
        + summary['Total_Count'].astype(str) + ' Students'
    )

    # Top summary metrics
    total_sessions = len(summary)
    total_student_checks = summary['Total_Count'].sum()
    total_present_checks = summary['Present_Count'].sum()
    avg_rate = round((total_present_checks / total_student_checks * 100), 1) if total_student_checks > 0 else 0

    m1, m2, m3 = st.columns(3)
    with m1:
        st.markdown(f"""
        <div class="metric-card">
            <span class="label">Total Sessions</span>
            <span class="value">{total_sessions}</span>
        </div>
        """, unsafe_allow_html=True)
    with m2:
        st.markdown(f"""
        <div class="metric-card">
            <span class="label">Total Attendances Logged</span>
            <span class="value">{total_present_checks} <span style="font-size: 1rem; color: #64748B; font-weight: 500;">/ {total_student_checks}</span></span>
        </div>
        """, unsafe_allow_html=True)
    with m3:
        st.markdown(f"""
        <div class="metric-card">
            <span class="label">Average Attendance Rate</span>
            <span class="value">{avg_rate}%</span>
        </div>
        """, unsafe_allow_html=True)

    st.write("")

    display_df = (summary.sort_values(by='ts_group', ascending=False)
                  [['Date & Time', 'Subject', 'Subject Code', 'Attendance Breakdown', 'Attendance Rate']])

    # CSV Export Button
    c_left, c_right = st.columns([3, 1], vertical_alignment='center')
    with c_left:
        st.markdown("**Session History Summary**")
    with c_right:
        csv_data = display_df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="Export as CSV",
            data=csv_data,
            file_name=f"attendance_summary_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
            mime="text/csv",
            icon=":material/download:",
            type="primary",
            width="stretch"
        )

    st.dataframe(display_df, width='stretch', hide_index=True)


def login_teacher(username, password):
    if not username or not password:
        return False
    teacher = teacher_login(username.strip(), password)
    if teacher:
        st.session_state.user_role = 'teacher'
        st.session_state.teacher_data = teacher
        st.session_state.is_logged_in = True
        return True
    return False


def teacher_screen_login():
    c1, c2 = st.columns([3, 1], vertical_alignment='center')
    with c1:
        header_dashboard()
    with c2:
        if st.button("Back to Home", type='secondary', key='teacher_home_btn', icon=':material/arrow_back:'):
            st.session_state['login_type'] = None
            st.rerun()

    st.write("")
    st.markdown("<h2 style='text-align: center;'>Teacher Portal Login</h2>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: #64748B;'>Sign in to manage courses, verify attendance, and view analytics.</p>", unsafe_allow_html=True)

    col_center = st.columns([1, 2, 1])[1]
    with col_center:
        with st.container():
            teacher_username = st.text_input("Username", placeholder="e.g. prof_anderson")
            teacher_pass = st.text_input("Password", type='password', placeholder="••••••••")

            st.write("")
            btnc1, btnc2 = st.columns(2, gap="small")
            with btnc1:
                if st.button('Sign In', type='primary', icon=':material/login:', width='stretch'):
                    if login_teacher(teacher_username, teacher_pass):
                        st.toast("Welcome back!", icon="👋")
                        time.sleep(0.5)
                        st.rerun()
                    else:
                        st.error("Invalid username or password.")
            with btnc2:
                if st.button('Create Account', type="secondary", width='stretch'):
                    st.session_state.teacher_login_type = 'register'
                    st.rerun()

    footer_dashboard()


def register_teacher(teacher_username, teacher_name, teacher_pass, teacher_pass_confirm):
    if not teacher_username or not teacher_name or not teacher_pass:
        return False, "All fields are required!"
    if check_teacher_exists(teacher_username.strip()):
        return False, "Username is already taken. Please choose another."
    if teacher_pass != teacher_pass_confirm:
        return False, "Passwords do not match."
    
    try:
        create_teacher(teacher_username.strip(), teacher_pass, teacher_name.strip())
        return True, "Account created successfully! You can now log in."
    except Exception as e:
        return False, f"Unexpected error: {str(e)}"


def teacher_screen_register():
    c1, c2 = st.columns([3, 1], vertical_alignment='center')
    with c1:
        header_dashboard()
    with c2:
        if st.button("Back to Home", type='secondary', key='reg_back_btn', icon=':material/arrow_back:'):
            st.session_state['login_type'] = None
            st.rerun()

    st.write("")
    st.markdown("<h2 style='text-align: center;'>Teacher Registration</h2>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: #64748B;'>Create an instructor profile to start conducting AI-powered classes.</p>", unsafe_allow_html=True)

    col_center = st.columns([1, 2, 1])[1]
    with col_center:
        with st.container():
            teacher_username = st.text_input("Username *", placeholder="e.g. prof_anderson")
            teacher_name = st.text_input("Full Name *", placeholder="e.g. Dr. Emily Anderson")
            teacher_pass = st.text_input("Password *", type='password', placeholder="••••••••")
            teacher_pass_confirm = st.text_input("Confirm Password *", type='password', placeholder="••••••••")

            st.write("")
            btnc1, btnc2 = st.columns(2, gap="small")
            with btnc1:
                if st.button('Register Profile', type='primary', icon=':material/person_add:', width='stretch'):
                    success, message = register_teacher(teacher_username, teacher_name, teacher_pass, teacher_pass_confirm)
                    if success:
                        st.success(message)
                        time.sleep(1.2)
                        st.session_state.teacher_login_type = "login"
                        st.rerun()
                    else:
                        st.error(message)
            with btnc2:
                if st.button('Sign In Instead', type="secondary", width='stretch'):
                    st.session_state.teacher_login_type = 'login'
                    st.rerun()

    footer_dashboard()