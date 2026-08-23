import streamlit as st

def header_home():
    logo_url = "https://i.ibb.co/YTYGn5qV/logo.png"
    
    st.markdown(f"""
        <div style="display: flex; flex-direction: column; align-items: center; justify-content: center; margin-bottom: 2rem; margin-top: 1rem; text-align: center;">
            <div style="background: rgba(255, 255, 255, 0.15); padding: 16px; border-radius: 24px; backdrop-filter: blur(10px); border: 1px solid rgba(255, 255, 255, 0.3); box-shadow: 0 10px 25px rgba(0,0,0,0.1); margin-bottom: 12px;">
                <img src='{logo_url}' style='height: 80px; filter: drop-shadow(0 4px 6px rgba(0,0,0,0.1));' alt='SnapClass Logo' />
            </div>
            <h1 style='color: white; margin: 0; text-shadow: 0 2px 10px rgba(0,0,0,0.15); font-size: 3rem;'>SNAPCLASS</h1>
            <p style='color: rgba(255, 255, 255, 0.9); font-size: 1.15rem; font-weight: 500; margin-top: 6px;'>Next-Gen Attendance Powered by Multimodal AI</p>
        </div>   
    """, unsafe_allow_html=True)


def header_dashboard():
    logo_url = "https://i.ibb.co/YTYGn5qV/logo.png"
    
    st.markdown(f"""
        <div style="display: flex; align-items: center; gap: 14px; padding: 0.5rem 0;">
            <div style="background: #EEF2FF; padding: 10px; border-radius: 16px; border: 1px solid #C7D2FE;">
                <img src='{logo_url}' style='height: 48px;' alt='SnapClass' />
            </div>
            <div>
                <h2 style='margin: 0; color: #4F46E5; font-size: 1.75rem; font-weight: 800;'>SNAPCLASS</h2>
                <p style='margin: 0; color: #64748B; font-size: 0.85rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em;'>AI Attendance System</p>
            </div>
        </div>   
    """, unsafe_allow_html=True)
