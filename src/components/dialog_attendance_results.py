import streamlit as st
from src.database.db import create_attendance

def show_attendance_result(df, logs):
    st.write('Review detected students before saving the attendance session.')

    present_count = sum(1 for log in logs if log.get('is_present'))
    total_count = len(logs)
    
    st.info(f"📊 **Summary:** {present_count} Present / {total_count - present_count} Absent out of {total_count} enrolled students.")
    st.dataframe(df, hide_index=True, width='stretch')

    col1, col2 = st.columns(2, gap="medium")

    with col1:
        if st.button('Discard', width='stretch', type='secondary', icon=':material/close:'):
            st.session_state.voice_attendance_results = None
            st.session_state.attendance_images = []
            st.rerun()

    with col2:
        if st.button('Confirm & Save Log', width='stretch', type='primary', icon=':material/check:'):
            try:
                create_attendance(logs)
                st.toast("Attendance session saved successfully!", icon="🎉")
                st.session_state.attendance_images = []
                st.session_state.voice_attendance_results = None
                st.rerun()
            except Exception as e:
                st.error(f'Sync failed: {str(e)}')

@st.dialog("Attendance Verification")
def attendance_result_dialog(df, logs):
    show_attendance_result(df, logs)
