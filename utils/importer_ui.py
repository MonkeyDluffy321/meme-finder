"""Import dialog, independent of discovery and creator state."""

import streamlit as st

from utils.importer import ImportError, import_meme


@st.dialog("Import Meme")
def render_importer():
    st.caption("Upload JPEG, PNG or static WebP, up to 10 MB and 20 megapixels.")
    with st.form("importer_form"):
        upload = st.file_uploader("Meme image", type=["jpg", "jpeg", "png", "webp"],
                                  key="importer_image")
        metadata = {
            "name": st.text_input("Name", key="importer_name"),
            "meaning": st.text_area("Meaning", key="importer_meaning"),
        }
        st.caption("Separate list values with commas. All fields except aliases are required.")
        for field in ("keywords", "situations", "emotions", "categories", "aliases"):
            metadata[field] = st.text_input(field.title(), key=f"importer_{field}")
        submitted = st.form_submit_button("Import", type="primary")
    if submitted:
        try:
            record = import_meme(metadata, upload.getvalue() if upload is not None else b"")
        except ImportError as error:
            st.error(str(error))
            return
        st.session_state.importer_notice = f"Imported {record['name']}. It is now available in search."
        st.rerun()
