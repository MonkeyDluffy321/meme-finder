"""Result actions reuse displayed bytes; they never fetch image URLs."""

from io import BytesIO

from PIL import Image
import streamlit as st

from utils.creator_ui import open_template_creator
from utils.uploads import validate_upload


def render_result_actions(preview, key, template=None):
    try:
        validate_upload(preview)
        with Image.open(BytesIO(preview)) as image:
            extension, mime = {"PNG": ("png", "image/png"),
                               "JPEG": ("jpg", "image/jpeg"),
                               "WEBP": ("webp", "image/webp")}[image.format]
    except Exception:
        preview = None

    if preview is None:
        st.button("Download", key="download-" + key, disabled=True,
                  help="Image unavailable for download.")
    else:
        st.download_button("Download", data=preview, file_name=f"meme.{extension}",
                           mime=mime, key="download-" + key, on_click="ignore")
    if template is not None:
        st.button("Create Meme", key="create-" + key, disabled=preview is None,
                  on_click=open_template_creator, args=(template, preview))
