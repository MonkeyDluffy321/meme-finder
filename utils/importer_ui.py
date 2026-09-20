"""Import dialog, independent of discovery and creator state."""

import streamlit as st

from utils.importer import ImportError, import_meme
from utils.importer_url import import_meme_url


@st.dialog("Import Meme")
def render_importer():
    st.caption("Upload JPEG, PNG or static WebP, up to 10 MB and 20 megapixels.")
    with st.form("importer_form"):
        upload = st.file_uploader("Meme image", type=["jpg", "jpeg", "png", "webp"],
                                  key="importer_image")
        url = st.text_input("Image URL (optional)", key="importer_url",
                            help="Direct HTTP/HTTPS image URL. Upload a file or enter a URL, not both.")
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
            if url.strip() and upload is not None:
                raise ImportError("Choose either an uploaded image or an Image URL.")
            if url.strip():
                record = import_meme_url(metadata, url.strip())
            else:
                record = import_meme(metadata, upload.getvalue() if upload is not None else b"")
        except ImportError as error:
            st.error(str(error))
            return
        st.session_state.importer_notice = f"Imported {record['name']}. It is now available in search."
        st.rerun()
