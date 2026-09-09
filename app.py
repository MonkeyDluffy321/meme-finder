"""Meme Finder: a small, completely local Streamlit app."""

import json
from pathlib import Path

import streamlit as st

from utils.search import search_memes


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
        st.subheader(meme["name"])
        st.write(f"**Meaning:** {meme['meaning']}")
        st.write(f"**Keywords:** {', '.join(meme['keywords'])}")
        st.write(f"**Description:** {meme['description']}")

st.caption("This first version searches text in a small sample dataset; it does not identify images.")
