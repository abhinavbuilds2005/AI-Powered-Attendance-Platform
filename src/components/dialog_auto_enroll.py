import streamlit as st
from src.database.db import enroll_student_to_subject
from src.database.config import supabase
import time

@st.dialog("Quick Course Enrollment")
def auto_enroll_dialog(subject_code):
    student_id = st.session_state.student_data['student_id']

    res = supabase.table('subjects').select('subject_id, name, subject_code').eq('subject_code', subject_code.strip().upper()).execute()
    if not res.data:
        st.error(f"Course Code **{subject_code}** was not found.")
        if st.button('Dismiss'):
            st.query_params.clear()
            st.rerun()
        return

    subject = res.data[0]

    check = supabase.table('subject_students').select('*').eq('subject_id', subject['subject_id']).eq('student_id', student_id).execute()
    if check.data:
        st.info(f"You are already enrolled in **{subject['name']}**.")
        if st.button('Continue to Dashboard', type='primary'):
            st.query_params.clear()
            st.rerun()
        return

    st.markdown(f"Would you like to enroll in **{subject['name']}** (`{subject['subject_code']}`)?")

    st.write("")
    col1, col2 = st.columns(2, gap="medium")

    with col1:
        if st.button('No, Skip', type='secondary', width='stretch'):
            st.query_params.clear()
            st.rerun()

    with col2:
        if st.button('Yes, Enroll Now', type='primary', width='stretch', icon=':material/check_circle:'):
            enroll_student_to_subject(student_id, subject['subject_id'])
            st.success(f"Joined **{subject['name']}** successfully!")
            st.query_params.clear()
            time.sleep(1.2)
            st.rerun()
