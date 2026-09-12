"""Meme Finder: local text search with remote template previews."""

import json
from io import BytesIO
from pathlib import Path

import streamlit as st

from utils.search import search_memes
from utils.images import load_preview


DATA_PATH = Path(__file__).parent / "data" / "memes.json"

st.set_page_config(page_title="Meme Finder", page_icon="🔎", layout="centered")

with st.sidebar:
    st.title("🔎 Meme Finder")
    st.caption("Your local meme reference")
    st.divider()
    st.subheader("Planned features")
    st.markdown(
        "- Upload & identify meme\n"
        "- Explain meme\n"
        "- Similar memes\n"
        "- Meme creator"
    )
    st.caption("Coming later — these features are not available yet.")

st.title("Find the meme you have in mind")
st.write("Search by template name, keywords, or a description of the scene.")
st.caption("Local sample collection · No accounts or API keys needed")

try:
    memes = json.loads(DATA_PATH.read_text(encoding="utf-8"))
except (OSError, json.JSONDecodeError):
    st.error("Could not load the sample dataset. Check data/memes.json and restart.")
    st.stop()

query = st.text_input(
    "Search memes",
    placeholder="Try distracted boyfriend, this is fine, or guy looking at another girl",
)

results = search_memes(memes, query)
if query.strip():
    st.subheader(f"{len(results)} result{'s' if len(results) != 1 else ''}")
else:
    st.subheader("Browse the sample collection")

if not results:
    st.info("No matching memes yet. Try fewer words, a template name, or another description.")

for meme in results:
    with st.container(border=True):
        preview_column, details_column = st.columns([2, 3], gap="medium")
        with details_column:
            st.subheader(meme["name"])
            st.write(meme["meaning"])
            if meme.get("aliases"):
                st.caption("Also known as: " + ", ".join(meme["aliases"]))
            if meme.get("categories"):
                st.write("**Categories:** " + ", ".join(meme["categories"]))
            if meme.get("situations"):
                st.markdown("**Common situations**")
                st.markdown("\n".join("- " + situation for situation in meme["situations"]))
            st.caption("Keywords: " + ", ".join(meme["keywords"]))
            with st.expander("Scene description"):
                st.write(meme["description"])
        with preview_column:
            preview = load_preview(meme.get("image_url"))
            if preview is None:
                st.caption("Preview unavailable")
            else:
                try:
                    st.image(BytesIO(preview), caption=meme["name"], width=240)
                except Exception:
                    # A corrupt or unsupported image must not hide the result text.
                    st.caption("Preview unavailable")

st.caption("Template previews hosted by Imgflip.")
