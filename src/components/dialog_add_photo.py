import streamlit as st
from PIL import Image

@st.dialog("Add Classroom Photos")
def add_photos_dialog():
    st.write('Capture a snapshot via webcam or upload high-resolution classroom images.')

    if 'photo_tab' not in st.session_state:
        st.session_state.photo_tab = 'camera'

    t1, t2 = st.columns(2, gap="small")

    with t1:
        type_camera = "primary" if st.session_state.photo_tab == 'camera' else 'secondary'
        if st.button('📸 Live Camera', type=type_camera, width='stretch'):
            st.session_state.photo_tab = 'camera'
            st.rerun()

    with t2:
        type_upload = "primary" if st.session_state.photo_tab == 'upload' else 'secondary'
        if st.button('📁 Upload Images', type=type_upload, width='stretch'):
            st.session_state.photo_tab = 'upload'
            st.rerun()

    st.write("")

    if st.session_state.photo_tab == 'camera':
        cam_photo = st.camera_input('Take Classroom Snapshot', key='dialog_cam')
        if cam_photo:
            st.session_state.attendance_images.append(Image.open(cam_photo))
            st.toast('Classroom photo captured!', icon="📸")
            st.rerun()

    if st.session_state.photo_tab == 'upload':
        uploaded_files = st.file_uploader('Select image files', type=['jpg', 'png', 'jpeg'], accept_multiple_files=True, key='dialog_upload')
        if uploaded_files:
            for f in uploaded_files:
                st.session_state.attendance_images.append(Image.open(f))
            st.toast(f'{len(uploaded_files)} photos added!', icon="✅")
            st.rerun()

    st.divider()
    if st.button('Done & Return to Dashboard', type='primary', width='stretch', icon=':material/done:'):
        st.rerun()
