import streamlit as st
from src.database.db import enroll_student_to_subject
from src.database.config import supabase
import time

@st.dialog("Enroll in Course")
def enroll_dialog():
    st.write('Enter the unique Course Code provided by your instructor.')
    join_code = st.text_input('Course Code *', placeholder='e.g. CS101')

    st.write("")
    if st.button('Enroll Now', type='primary', width='stretch', icon=':material/how_to_reg:'):
        if join_code.strip():
            code_clean = join_code.strip().upper()
            res = supabase.table('subjects').select('subject_id, name, subject_code').eq('subject_code', code_clean).execute()
            if res.data:
                subject = res.data[0]
                student_id = st.session_state.student_data['student_id']

                check = supabase.table('subject_students').select('*').eq('subject_id', subject['subject_id']).eq('student_id', student_id).execute()
                if check.data:
                    st.warning(f"You are already enrolled in **{subject['name']}**.")
                else:
                    enroll_student_to_subject(student_id, subject['subject_id'])
                    st.success(f"Successfully enrolled in **{subject['name']}**!")
                    time.sleep(0.8)
                    st.rerun()
            else:
                st.error("No course found matching that subject code.")
        else:
            st.warning('Please enter a valid course code.')