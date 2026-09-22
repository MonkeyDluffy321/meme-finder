"""Finished-meme cards, independent of template/library actions."""

from io import BytesIO
import streamlit as st

from utils import images
from utils.result_actions import render_result_actions


def render_finished_memes(memes):
    if not memes:
        return
    st.subheader("Finished Memes")
    st.caption(f"{len(memes)} finished meme results")
    with st.container(key="finished-results"):
        for start in range(0, len(memes), 3):
            for column, meme in zip(st.columns(3), memes[start:start + 3]):
                with column, st.container(key="finished-" + meme["instance_key"]):
                    preview = None
                    try:
                        preview = images.load_external_preview(meme["image_url"])
                        if preview is None:
                            st.caption("Preview unavailable")
                        else:
                            st.image(BytesIO(preview), use_container_width=True)
                    except Exception:
                        st.caption("Preview unavailable")
                    st.text(meme["caption_text"] or "Caption unavailable")
                    if meme.get("template_name"):
                        st.text("Template: " + meme["template_name"])
                    st.text("Source: " + meme["provider"])
                    render_result_actions(preview, "finished-" + meme["instance_key"])
