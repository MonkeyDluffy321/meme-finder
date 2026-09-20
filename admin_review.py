"""Standalone admin app: streamlit run admin_review.py --server.address 127.0.0.1

Set MEME_FINDER_REVIEW_TOKEN to a long random secret before launching.
Populate via ReviewQueue().enqueue(crawl_result['candidates']).
"""

import hmac
import os

import streamlit as st

from utils.catalog_review import ReviewError, ReviewQueue
from utils.importer import LIST_FIELDS, normalize_list
from utils.importer_url import download_image
from utils.uploads import validate_upload


st.set_page_config(page_title="Internal catalog review")
expected = os.environ.get("MEME_FINDER_REVIEW_TOKEN", "")
if len(expected) < 24:
    st.error("Internal review is disabled. Configure MEME_FINDER_REVIEW_TOKEN (at least 24 characters).")
    st.stop()
token = st.text_input("Admin token", type="password", key="review_admin_token")
if not hmac.compare_digest(token.encode(), expected.encode()):
    st.info("Enter the admin token to access the queue.")
    st.stop()

st.title("Catalog Review Queue")
queue = ReviewQueue()
if notice := st.session_state.pop("review_notice", None):
    st.info(notice)
try:
    rows = queue.entries()
    view = st.selectbox("Status", ["pending", "error", "imported", "duplicate", "rejected"])
    visible = [row for row in rows if row["status"] == view]
    if not visible:
        st.info("No candidates with this status.")
        st.stop()
    lookup = {row["queue_id"]: row for row in visible}
    identity = st.selectbox("Candidate", list(lookup),
                            format_func=lambda key: lookup[key]["candidate"].get("name") or key[:12])
    row = lookup[identity]
    candidate = row["candidate"]
    st.write("Source page:", candidate.get("source_page", ""))
    st.write("Image URL:", candidate.get("source_image_url", ""))
    if row.get("result"):
        st.info(f"{row['status']}: {row['result'].get('message', '')}")
    if st.button("Load preview", key="preview-" + identity):
        try:
            upload = validate_upload(download_image(candidate["source_image_url"], respect_indexing=True))
            st.image(upload.preview)
        except Exception:
            st.warning("Preview unavailable.")
    if view == "error":
        if st.button("Retry review", key="retry-" + identity):
            queue.retry(identity)
            st.session_state.review_notice = "Returned to pending for explicit approval."
            st.rerun()
    if view not in {"pending", "error"}:
        st.json(candidate)
        st.stop()
    with st.form("review-" + identity):
        edits = {"name": st.text_input("Name", value=candidate.get("name", "")),
                 "meaning": st.text_area("Meaning", value=candidate.get("meaning", ""))}
        for field in LIST_FIELDS:
            edits[field] = normalize_list(st.text_area(field.title(), value=", ".join(candidate.get(field, []))))
        approve = st.form_submit_button("Approve", disabled=view != "pending")
        reject = st.form_submit_button("Reject")
    if approve or reject:
        result = queue.approve(identity, edits) if approve else queue.reject(identity)
        st.session_state.review_notice = f"{result['status']}: {result['message']}"
        st.rerun()
except (ReviewError, OSError, ValueError) as error:
    st.error(str(error))
