import streamlit as st
import segno
import io

@st.dialog("Share Class Invitation")
def share_subject_dialog(subject_name, subject_code):
    # Dynamic domain resolution or fallback
    app_domain = st.secrets.get("APP_DOMAIN", "localhost:8501")
    join_url = f"http://{app_domain}/?join-code={subject_code}" if not app_domain.startswith("http") else f"{app_domain}/?join-code={subject_code}"

    st.markdown(f"### Invite Students to **{subject_name}**")
    st.write("Share the QR code or link below with students for 1-click self-enrollment.")

    qr = segno.make(join_url)
    out = io.BytesIO()
    qr.save(out, kind='png', scale=8, border=2)

    col1, col2 = st.columns([1.2, 1], gap="medium")

    with col1:
        st.markdown("**Direct Join Link:**")
        st.code(join_url, language="text")
        
        st.markdown("**Subject Code:**")
        st.code(subject_code, language="text")
        st.caption("Students can enter this code in their portal or open the join link directly.")

    with col2:
        st.image(out.getvalue(), caption="Scan with mobile camera to enroll", width=180)
