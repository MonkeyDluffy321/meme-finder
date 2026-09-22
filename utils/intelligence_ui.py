"""Local OCR, template metadata and related meme interface."""

from hashlib import sha256
from io import BytesIO
import streamlit as st

from utils.uploads import validate_upload, UploadError
from utils.intelligence import analyze, reliable_template
from utils.explanations import explain, related_memes
from utils.identification import Identification
from utils.ocr import OCRResult
from utils.local_explainer import explain_local

CONTENT_KEYS = ("v3_validated", "v3_result", "v3_text", "v3_related", "v3_explanation", "v3_question")


def clear_image():
    generation = st.session_state.get("v3_generation", 0) + 1
    for key in list(st.session_state):
        if key.startswith("v3_"):
            del st.session_state[key]
    st.session_state.v3_generation = generation


def discard_related():
    # A changed caption invalidates prior results.
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
    with st.expander("Analyze a Meme", expanded=False):
        st.caption("Read visible text, identify local templates and explain memes using local collection metadata.")
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
        st.caption("Preview and OCR run locally on this app's server.")
        if st.button("Read text locally", key="v3_analyze"):
            with st.spinner("Reading visible text locally…"):
                result = analyze(upload, memes)
            st.session_state.v3_result = result
            st.session_state.v3_text = result["ocr"].text
            discard_related()
        result = st.session_state.get("v3_result", {
            "ocr": OCRResult("not_run"), "identification": Identification("unavailable"), "notices": []})
        st.markdown("**Visible text**")
        messages = {"not_run": "Read text locally above, or type it below.",
                    "empty": "No readable text detected. You can type a caption below.",
                    "unavailable": "OCR unavailable. You can still type the caption to find related memes.",
                    "failed": "Text extraction failed. You can still type the caption.",
                    "uncertain": "Some detected text may be inaccurate. Please check it."}
        if result["ocr"].status in messages:
            st.caption(messages[result["ocr"].status])
        st.session_state.setdefault("v3_text", result["ocr"].text)
        st.text_area("Check or correct the visible text (optional)", key="v3_text", max_chars=5000,
                     on_change=discard_related)
        st.text_input("Local question (optional)", key="v3_question", max_chars=500,
                      placeholder="What does this meme mean?", on_change=discard_related)
        if st.button("Explain meme", key="v3_explain"):
            correction = st.session_state.v3_text
            if correction == result["ocr"].text:
                correction = None
            st.session_state.v3_explanation = explain_local(
                result, memes, corrected_text=correction, question=st.session_state.v3_question)
        local_explanation = st.session_state.get("v3_explanation")
        if local_explanation is not None:
            explanation = local_explanation.explanation
            st.markdown("### Local explanation")
            st.text(explanation.answer)
            if explanation.intent not in ("overview", "meaning"):
                st.text(explanation.expression)
            st.text(explanation.observations)
            if explanation.intent != "humor":
                st.text(explanation.why_it_works)
            if explanation.intent != "caption":
                for wording in explanation.wording:
                    st.text(wording)
            if explanation.intent != "usage" and explanation.situations:
                st.text("Documented situations:\n" + "\n".join(explanation.situations))
            if explanation.intent != "similar" and explanation.related:
                st.text("Related collection suggestions (not image identifications):\n" +
                        "\n".join(meme["name"] for meme in explanation.related))
            st.caption(explanation.uncertainty)
            if explanation.template_name:
                st.text("Template: " + explanation.template_name + " (supporting context)")
        matched = reliable_template(result, memes)
        with st.expander("Template context", expanded=False):
            identity = result["identification"]
            st.caption("Local collection metadata; the exact uploaded joke is not interpreted.")
            if matched:
                render_metadata(matched)
            elif identity.status == "possible" and identity.candidates:
                names = {m["id"]: m["name"] for m in memes}
                st.caption("Possible match: " + names.get(identity.candidates[0]["id"], "Unknown") +
                           ". Too uncertain to identify reliably.")
            else:
                st.caption("No reliable match. You can still search for related memes using visible text.")
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
