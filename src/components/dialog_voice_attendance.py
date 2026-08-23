import streamlit as st
from src.pipelines.voice_pipeline import process_bulk_audio
from src.database.config import supabase
import pandas as pd
from src.components.dialog_attendance_results import show_attendance_result
from datetime import datetime

@st.dialog('Voice Attendance Studio')
def voice_attendance_dialog(selected_subject_id):
    st.write('Record classroom audio of students declaring attendance (e.g. *"I am present, my name is Alex"*).')
    st.caption('The AI will extract acoustic voice prints, match them against registered student embeddings, and log attendance.')

    audio_data = None
    try:
        audio_data = st.audio_input("Record Classroom Audio", key="voice_att_recorder")
    except Exception:
        st.error("Audio recording input is not available.")

    if audio_data and st.button('Analyze Classroom Audio', width='stretch', type='primary', icon=':material/graphic_eq:'):
        with st.spinner('Segmenting audio stream and extracting acoustic embeddings...'):
            enrolled_res = supabase.table('subject_students').select("*, students(*)").eq('subject_id', selected_subject_id).execute()
            enrolled_students = enrolled_res.data or []

            if not enrolled_students:
                st.warning('No students are currently enrolled in this course.')
                return

            candidates_dict = {
                s['students']['student_id']: s['students']['voice_embedding']
                for s in enrolled_students if s['students'].get('voice_embedding')
            }

            if not candidates_dict:
                st.error('None of the enrolled students have voice biometric profiles registered.')
                return

            audio_bytes = audio_data.read()
            detected_scores = process_bulk_audio(audio_bytes, candidates_dict)

            results, attendance_to_log = [], []
            current_timestamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

            for node in enrolled_students:
                student = node['students']
                score = detected_scores.get(student['student_id'], 0.0)
                is_present = bool(score > 0)

                results.append({
                    "Name": student['name'],
                    "ID": student['student_id'],
                    "Match Score": f"{round(score * 100, 1)}%" if is_present else "-",
                    "Status": "✅ Present" if is_present else "❌ Absent"
                })

                attendance_to_log.append({
                    'student_id': student['student_id'],
                    'subject_id': selected_subject_id,
                    'timestamp': current_timestamp,
                    'is_present': bool(is_present)
                })

            st.session_state.voice_attendance_results = (pd.DataFrame(results), attendance_to_log)

    if st.session_state.get('voice_attendance_results'):
        st.divider()
        df_results, logs = st.session_state.voice_attendance_results
        show_attendance_result(df_results, logs)
