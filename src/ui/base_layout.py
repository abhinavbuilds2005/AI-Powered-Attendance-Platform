import streamlit as st

def style_background_home():
    st.markdown("""
        <style>
            .stApp {
                background: linear-gradient(135deg, #4338CA 0%, #3B82F6 50%, #6366F1 100%) !important;
                background-attachment: fixed !important;
            }

            .stApp div[data-testid="stColumn"] {
                background: rgba(255, 255, 255, 0.95) !important;
                backdrop-filter: blur(12px) !important;
                padding: 2.5rem !important;
                border-radius: 2rem !important;
                box-shadow: 0 20px 40px -15px rgba(0, 0, 0, 0.25) !important;
                border: 1px solid rgba(255, 255, 255, 0.6) !important;
                transition: transform 0.3s ease, box-shadow 0.3s ease !important;
            }

            .stApp div[data-testid="stColumn"]:hover {
                transform: translateY(-4px) !important;
                box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.35) !important;
            }
        </style>
    """, unsafe_allow_html=True)


def style_background_dashboard():
    st.markdown("""
        <style>
            .stApp {
                background: #F8FAFC !important;
                background-attachment: fixed !important;
            }
        </style>
    """, unsafe_allow_html=True)


def style_base_layout():
    st.markdown("""
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@400;500;600;700;800;900&family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap');

            /* Hide Top Bar & Streamlit branding */
            #MainMenu, footer, header {
                visibility: hidden !important;
            }

            html, body, [class*="css"] {
                font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif;
                color: #1E293B;
            }

            .block-container {
                padding-top: 2rem !important;
                padding-bottom: 3rem !important;
                max-width: 1100px !important;
            }

            h1 {
                font-family: 'Outfit', sans-serif !important;
                font-weight: 800 !important;
                font-size: 3rem !important;
                line-height: 1.15 !important;
                letter-spacing: -0.02em !important;
                margin-bottom: 0.5rem !important;
            }

            h2 {
                font-family: 'Outfit', sans-serif !important;
                font-weight: 700 !important;
                font-size: 1.85rem !important;
                line-height: 1.25 !important;
                letter-spacing: -0.01em !important;
                color: #0F172A !important;
                margin-bottom: 0.5rem !important;
            }

            h3 {
                font-family: 'Outfit', sans-serif !important;
                font-weight: 600 !important;
                font-size: 1.35rem !important;
                color: #1E293B !important;
            }

            h4, p, label {
                font-family: 'Plus Jakarta Sans', sans-serif !important;
            }

            /* Custom UI Buttons */
            button {
                border-radius: 1rem !important;
                font-family: 'Plus Jakarta Sans', sans-serif !important;
                font-weight: 600 !important;
                padding: 0.65rem 1.4rem !important;
                border: 1px solid transparent !important;
                transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1) !important;
            }

            button:hover {
                transform: translateY(-2px) !important;
                box-shadow: 0 8px 20px -6px rgba(79, 70, 229, 0.35) !important;
            }

            button[kind="primary"] {
                background: linear-gradient(135deg, #4F46E5 0%, #6366F1 100%) !important;
                color: white !important;
                box-shadow: 0 4px 14px 0 rgba(79, 70, 229, 0.3) !important;
            }

            button[kind="secondary"] {
                background: white !important;
                color: #4F46E5 !important;
                border: 1.5px solid #E0E7FF !important;
            }

            button[kind="secondary"]:hover {
                background: #EEF2FF !important;
                border-color: #C7D2FE !important;
            }

            button[kind="tertiary"] {
                background: #0F172A !important;
                color: #F8FAFC !important;
            }

            /* Modern Streamlit Input Fields */
            .stTextInput>div>div>input, .stSelectbox>div>div>div {
                border-radius: 0.85rem !important;
                border: 1.5px solid #E2E8F0 !important;
                padding: 0.6rem 1rem !important;
                font-family: 'Plus Jakarta Sans', sans-serif !important;
                background-color: #FFFFFF !important;
                transition: all 0.2s ease !important;
            }

            .stTextInput>div>div>input:focus {
                border-color: #6366F1 !important;
                box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.15) !important;
            }

            /* Camera & Media Input Card Framing */
            div[data-testid="stCameraInput"] {
                border-radius: 1.25rem !important;
                overflow: hidden !important;
                border: 2px dashed #6366F1 !important;
                background: rgba(99, 102, 241, 0.03) !important;
                padding: 1rem !important;
            }

            /* Modern Metric / Stats Box */
            .metric-card {
                background: white;
                border-radius: 1.25rem;
                padding: 1.25rem 1.5rem;
                border: 1px solid #E2E8F0;
                box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
                display: flex;
                flex-direction: column;
                gap: 0.35rem;
            }

            .metric-card .value {
                font-family: 'Outfit', sans-serif;
                font-size: 2rem;
                font-weight: 800;
                color: #4F46E5;
                line-height: 1;
            }

            .metric-card .label {
                font-size: 0.875rem;
                font-weight: 600;
                color: #64748B;
                text-transform: uppercase;
                letter-spacing: 0.05em;
            }

            /* Status Badges */
            .badge-present {
                display: inline-flex;
                align-items: center;
                gap: 0.35rem;
                padding: 0.25rem 0.75rem;
                border-radius: 9999px;
                font-size: 0.85rem;
                font-weight: 600;
                background: #DCFCE7;
                color: #15803D;
            }

            .badge-absent {
                display: inline-flex;
                align-items: center;
                gap: 0.35rem;
                padding: 0.25rem 0.75rem;
                border-radius: 9999px;
                font-size: 0.85rem;
                font-weight: 600;
                background: #FEE2E2;
                color: #B91C1C;
            }
        </style>
    """, unsafe_allow_html=True)