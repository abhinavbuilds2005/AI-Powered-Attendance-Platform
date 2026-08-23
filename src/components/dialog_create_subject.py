import streamlit as st
from src.database.db import create_subject
import time

@st.dialog("Create New Subject")
def create_subject_dialog(teacher_id):
    st.write("Fill in the course details below.")
    sub_id = st.text_input("Subject / Course Code *", placeholder="e.g. CS101")
    sub_name = st.text_input("Course Name *", placeholder="e.g. Introduction to Computer Science")
    sub_section = st.text_input("Section / Group *", placeholder="e.g. A")

    st.write("")
    if st.button("Create Course", type='primary', width='stretch', icon=':material/add_circle:'):
        if sub_id.strip() and sub_name.strip() and sub_section.strip():
            try:
                create_subject(sub_id.strip().upper(), sub_name.strip(), sub_section.strip().upper(), teacher_id)
                st.toast("Course created successfully!", icon="🎉")
                time.sleep(0.5)
                st.rerun()
            except Exception as e:
                st.error(f"Error creating course: {str(e)}")
        else:
            st.warning("Please fill in all mandatory fields.")
