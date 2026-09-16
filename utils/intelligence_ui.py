"""Explanation-first interface. Only the Explain button invokes a cloud provider."""

from hashlib import sha256
from io import BytesIO
import streamlit as st

from utils.uploads import validate_upload, UploadError
from utils.intelligence import analyze, explain_upload, reliable_template
from utils.explanations import explain, related_memes
from utils.identification import Identification
from utils.ocr import OCRResult

CONTENT_KEYS = ("v3_validated", "v3_result", "v3_text", "v3_related", "v3_explanation")


def clear_image():
    generation = st.session_state.get("v3_generation", 0) + 1
    for key in list(st.session_state):
        if key.startswith("v3_"):
            del st.session_state[key]
    st.session_state.v3_generation = generation


def discard_related():
    # A changed caption invalidates both outputs; it never triggers a request.
    st.session_state.pop("v3_related", None)
    st.session_state.pop("v3_explanation", None)


def render_metadata(matched):
    metadata = explain(matched)
    st.write(metadata["name"])
    st.write(metadata["description"])
    st.write(metadata["meaning"])
    for situation in metadata["situations"]:
        st.write("• " + situation)


def render_intelligence(memes):
    with st.expander("Explain a Meme", expanded=False):
        st.caption("Understand what an image expresses, how its joke or reaction works, and what may need more context.")
        generation = st.session_state.get("v3_generation", 0)
        uploaded = st.file_uploader("Meme image", type=["jpg", "jpeg", "png", "webp"],
                                    key=f"v3_upload_{generation}")
        if uploaded is None:
            for key in (*CONTENT_KEYS, "v3_digest"):
                st.session_state.pop(key, None)
            return
        content = uploaded.getvalue()
        digest = sha256(content).hexdigest()
        if st.session_state.get("v3_digest") != digest:
            for key in CONTENT_KEYS:
                st.session_state.pop(key, None)
            st.session_state.v3_digest = digest
            try:
                st.session_state.v3_validated = validate_upload(content)
            except UploadError as error:
                st.error(str(error))
        st.button("Clear image", key="v3_clear", on_click=clear_image)
        upload = st.session_state.get("v3_validated")
        if upload is None:
            st.caption("Choose a different JPEG, PNG or static WebP image.")
            return
        st.image(BytesIO(upload.preview), width=500)
        st.caption("Preview and OCR run locally on this app's server. No image is sent to Gemini until you click Explain this meme.")
        if st.button("Read text locally", key="v3_analyze"):
            with st.spinner("Reading visible text locally…"):
                result = analyze(upload, memes)
            st.session_state.v3_result = result
            st.session_state.v3_text = result["ocr"].text
            discard_related()
        result = st.session_state.get("v3_result", {
            "ocr": OCRResult("not_run"), "identification": Identification("unavailable"), "notices": []})
        st.markdown("**Visible text**")
        messages = {"not_run": "Read text locally above, or type it below. You can also explain the image without OCR.",
                    "empty": "No readable text detected. You can type a caption below.",
                    "unavailable": "OCR unavailable. You can still request a visual explanation or type the caption.",
                    "failed": "Text extraction failed. Visual explanation is still available.",
                    "uncertain": "Some detected text may be inaccurate. Please check it."}
        if result["ocr"].status in messages:
            st.caption(messages[result["ocr"].status])
        st.session_state.setdefault("v3_text", result["ocr"].text)
        st.text_area("Check or correct the visible text (optional)", key="v3_text", max_chars=5000,
                     on_change=discard_related)
        st.info("Pressing Explain this meme sends the normalized image, visible/corrected text, and any reliable template hint to Google Gemini. Google processes this content under its API terms; free-tier content may be used to improve its products. The app does not save your image or explanation to disk or Supabase.")
        if st.button("Explain this meme", key="v3_explain", type="primary"):
            with st.spinner("Explaining with Gemini…"):
                st.session_state.v3_explanation = explain_upload(
                    upload, result, memes, st.session_state.v3_text)
        vision = st.session_state.get("v3_explanation")
        matched = reliable_template(result, memes)
        if vision is not None:
            if vision.status == "ok" and vision.explanation is not None:
                st.markdown("### Explanation")
                explanation = vision.explanation
                for title, value in [("What is visible", explanation.observations),
                                     ("What it appears to express", explanation.expression),
                                     ("Why the joke or reaction works", explanation.why_it_works)]:
                    st.markdown("**" + title + "**")
                    st.text(value)
                if explanation.wording:
                    st.markdown("**Wording, slang or references**")
                    for wording in explanation.wording:
                        st.text(wording)
                st.markdown("**Uncertainty / missing context**")
                st.text(explanation.uncertainty)
                st.caption("This is a model interpretation, not a verified account of intent or history.")
            else:
                st.warning(vision.message or "Cloud explanation unavailable.")
                st.markdown("### Limited explanation available")
                if matched:
                    st.caption("General collection metadata for a reliable template match; the exact uploaded joke is not interpreted.")
                    render_metadata(matched)
                else:
                    st.caption("Visible text remains editable. Without the vision provider or a reliable template match, the app cannot explain this image's context reliably.")
        with st.expander("Template context", expanded=False):
            identity = result["identification"]
            st.caption("Optional local collection evidence. A match is not required for an explanation.")
            if matched:
                render_metadata(matched)
            elif identity.status == "possible" and identity.candidates:
                names = {m["id"]: m["name"] for m in memes}
                st.caption("Possible match: " + names.get(identity.candidates[0]["id"], "Unknown") +
                           ". Too uncertain to use as an explanation hint.")
            else:
                st.caption("No reliable match. This does not limit Gemini's image explanation.")
            for notice in result["notices"]:
                st.caption(notice)
        with st.expander("Related memes", expanded=False):
            if st.button("Find related memes using this text", key="v3_find_related"):
                st.session_state.v3_related = related_memes(memes, matched, st.session_state.v3_text)
            related = st.session_state.get("v3_related")
            if related is None:
                related = related_memes(memes, matched)
            if not related:
                st.caption("Add or correct visible text and search for related templates.")
            for meme in related:
                st.write(meme["name"] + " — " + meme["meaning"])
