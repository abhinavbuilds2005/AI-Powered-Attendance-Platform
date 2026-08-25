import streamlit as st
from src.components.header import header_home
from src.components.footer import footer_home
from src.ui.base_layout import style_base_layout, style_background_home

def home_screen():
    header_home()
    style_background_home()
    style_base_layout()

    col1, col2 = st.columns(2, gap="large")

    with col1:
        st.markdown("""
        <div style="text-align: center; padding-bottom: 1rem;">
            <h2 style="color: #1E1B4B; margin-bottom: 0.25rem;">Student Portal</h2>
            <p style="color: #475569; font-size: 0.95rem;">Instant FaceID Login, course enrollments & attendance history</p>
        </div>
        """, unsafe_allow_html=True)
        
        c_img = st.columns([1, 2, 1])[1]
        with c_img:
            st.image("https://i.ibb.co/844D9Lrt/mascot-student.png", width=140)

        st.write("")
        if st.button('Enter as Student', type='primary', width='stretch', icon=':material/arrow_forward:'):
            st.session_state['login_type'] = 'student'
            st.rerun()

    with col2:
        st.markdown("""
        <div style="text-align: center; padding-bottom: 1rem;">
            <h2 style="color: #1E1B4B; margin-bottom: 0.25rem;">Teacher Studio</h2>
            <p style="color: #475569; font-size: 0.95rem;">AI Photo & Voice Scanning, Subject QR Generator & Analytics</p>
        </div>
        """, unsafe_allow_html=True)

        c_img = st.columns([1, 2, 1])[1]
        with c_img:
            st.image("https://i.ibb.co/CsmQQV6X/mascot-prof.png", width=155)

        st.write("")
        if st.button('Enter as Instructor', type='primary', width='stretch', icon=':material/arrow_forward:'):
            st.session_state['login_type'] = 'teacher'
            st.rerun()

    footer_home()