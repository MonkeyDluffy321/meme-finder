"""Library interactions; no user data or clients are globally cached."""

import streamlit as st

from utils.library import LibraryError, record_view, save_meme, unsave_meme


def navigate(view):
    st.session_state.library_view = view
    st.session_state.library_page = 0
    st.session_state.pop("library_notice", None)


def change_save(meme_id, saved):
    try:
        (unsave_meme if saved else save_meme)(st.session_state, meme_id)
        st.session_state.library_notice = "Meme unsaved." if saved else "Meme saved."
    except LibraryError as error:
        st.session_state.library_notice = str(error)


def toggle_details(meme_id):
    opened = set(st.session_state.get("library_open_details", set()))
    if meme_id in opened:
        opened.remove(meme_id)
        st.session_state.library_open_details = opened
        return
    opened.add(meme_id)
    st.session_state.library_open_details = opened
    try:
        record_view(st.session_state, meme_id)
    except LibraryError as error:
        st.session_state.library_notice = str(error)


def card_actions(meme, saved_ids):
    saved = meme["id"] in saved_ids
    st.button("Unsave" if saved else "Save", key="save-" + meme["id"],
              on_click=change_save, args=(meme["id"], saved))
    st.button("More details", key="details-" + meme["id"],
              on_click=toggle_details, args=(meme["id"],))
    return meme["id"] in st.session_state.get("library_open_details", set())
