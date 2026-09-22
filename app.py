"""Meme Finder: searchable template collection with remote previews."""

import json
from html import escape
from io import BytesIO
from pathlib import Path

import streamlit as st

from utils.filters import filter_memes, filter_options
from utils.images import load_preview, load_local_preview, load_external_preview
from utils.search import normalize_query
from utils.search_all import search_all
from utils.meme_results_ui import render_finished_memes
from utils.result_actions import render_result_actions
from utils.web_search import search_web
from utils.account_ui import render_account
from utils.auth import current_account
from utils.library import LibraryError, fetch_library, resolve_memes
from utils.library_ui import navigate, card_actions
from utils.intelligence_ui import render_intelligence
from utils.creator_ui import open_creator, render_creator
from utils.importer_ui import render_importer


DATA_PATH = Path(__file__).parent / "data" / "memes.json"
IMPORTED_DATA_PATH = Path(__file__).parent / "data" / "imported_memes.json"
PAGE_SIZE = 6

st.set_page_config(page_title="Meme Finder", page_icon=":material/image_search:", layout="wide")

st.html("<style>" + Path(__file__).with_name("ui.css").read_text(encoding="utf-8") + "</style>")


def reset_page():
    if st.session_state.get("library_view", "home") != "home":
        navigate("home")
    st.session_state.page = 0


def clear_search():
    st.session_state.query = ""
    reset_page()


def reset_filters():
    st.session_state.categories = []
    st.session_state.emotions = []
    st.session_state.quick_category = "All"
    st.session_state.quick_emotion = None
    reset_page()


def browse_all():
    show_library("home")
    clear_search()
    reset_filters()


def show_library(view):
    st.session_state.creator_active = False
    navigate(view)


def turn_page(offset):
    key = "library_page" if st.session_state.get("library_view", "home") != "home" else "page"
    st.session_state[key] += offset


def quick_category_changed():
    value = st.session_state.quick_category
    st.session_state.categories = [value] if value and value != "All" else []
    reset_page()


def quick_emotion_changed():
    value = st.session_state.quick_emotion
    st.session_state.emotions = [value] if value else []
    reset_page()


def advanced_filters_changed():
    st.session_state.quick_category = None
    st.session_state.quick_emotion = None
    reset_page()


try:
    memes = json.loads(DATA_PATH.read_text(encoding="utf-8"))

    if IMPORTED_DATA_PATH.exists():
        imported_memes = json.loads(
            IMPORTED_DATA_PATH.read_text(encoding="utf-8")
        )

        if isinstance(imported_memes, list):
            existing_ids = {meme["id"] for meme in memes}

            memes.extend(
                meme
                for meme in imported_memes
                if meme.get("id") not in existing_ids
            )

except (OSError, json.JSONDecodeError, TypeError, KeyError):
    st.error("The collection could not be loaded. Please try again later.")
    st.stop()

st.session_state.setdefault("page", 0)
st.session_state.setdefault("quick_category", "All")

with st.sidebar:
    with st.container(key="brand"):
        st.subheader(":material/image_search: Meme Finder")
        st.caption("Memes for every moment")
    with st.container(key="navigation"):
        st.button("Home", icon=":material/home:", on_click=browse_all,
                  type="secondary" if st.session_state.get("creator_active") else "primary",
                  use_container_width=True, key="home")
        st.button("Create", icon=":material/edit:", on_click=open_creator,
                  type="primary" if st.session_state.get("creator_active") else "secondary",
                  key="create", use_container_width=True)
        if st.button("Import Meme", icon=":material/upload:", key="import_meme",
                     use_container_width=True):
            render_importer()
        for label, icon in [("Explore", "explore"), ("Categories", "category")]:
            st.button(label, icon=f":material/{icon}:", disabled=True,
                      help="Not available in this prototype", use_container_width=True)
        st.button("Saved", icon=":material/bookmark:", on_click=show_library,
                  args=("saved",), key="saved", use_container_width=True)
        st.button("Recently Viewed", icon=":material/history:", on_click=show_library,
                  args=("recent",), key="recent", use_container_width=True)
    with st.container(key="product_info"):
        st.divider()
        st.caption("Meme Finder V3")
        st.caption(f"{len(memes)} templates in the collection")
        st.caption("Local discovery. No account needed.")
        st.caption("Previews hosted by Imgflip.")

if notice := st.session_state.pop("importer_notice", None):
    st.success(notice)

if st.session_state.get("creator_active", False):
    # Preserve discovery controls while their widgets are absent. Never assign
    # uploader state: creator images/captions live in the independent draft.
    for key in ("query", "categories", "emotions", "quick_category", "quick_emotion"):
        if key in st.session_state:
            st.session_state[key] = st.session_state[key]
    render_creator()
    st.stop()

st.html('''<header class="mf-hero">
<div class="eyebrow">MEMES CONNECT PEOPLE</div>
<h1>Find the meme<br><span>you have in mind</span></h1>
<p>Search by description, emotion, or situation.<br>
Because the perfect meme is always out there.</p></header>''')

with st.container(key="search_box"):
    input_column, search_column = st.columns([5, 1], vertical_alignment="bottom")
    with input_column:
        query = st.text_input("Find a meme", key="query", label_visibility="collapsed",
                              placeholder="e.g. awkward, productivity, monday, cat, success...",
                              on_change=reset_page)
    with search_column:
        st.button("Search", icon=":material/search:", type="primary",
                  on_click=reset_page, use_container_width=True)
with st.container(key="quick_filters"):
    category_options = filter_options(memes, "categories")
    quick_categories = [tag for tag in ["reaction", "work", "relationships", "success", "choice", "irony"]
                        if tag in category_options]
    st.pills("Quick categories", ["All"] + quick_categories, key="quick_category",
             on_change=quick_category_changed,
             format_func=str.title, label_visibility="collapsed")
    st.button("Clear search", icon=":material/close:", on_click=clear_search,
              disabled=not query, key="clear_search")

with st.expander("Advanced filters", expanded=False):
    category_column, emotion_column = st.columns(2)
    with category_column:
        categories = st.multiselect("Categories", filter_options(memes, "categories"),
                                    key="categories", on_change=advanced_filters_changed,
                                    placeholder="All categories")
    with emotion_column:
        emotions = st.multiselect("Emotions", filter_options(memes, "emotions"),
                                  key="emotions", on_change=advanced_filters_changed,
                                  placeholder="All emotions")
if categories or emotions:
    st.button("Reset filters", icon=":material/filter_alt_off:",
              on_click=reset_filters, key="reset_filters")

search_query = normalize_query(query)
is_home = st.session_state.get("library_view", "home") == "home"
groups = search_all(query, memes, include_finished=is_home, include_external=is_home)
finished_results = groups["memes"]
search_results = groups["templates"]
web_query = search_query.strip()
if st.session_state.get("live_web_search", {}).get("query") != web_query:
    st.session_state.live_web_search = {"query": web_query, "results": None}
web_cache = st.session_state.live_web_search
if (st.session_state.get("library_view", "home") == "home"
        and web_query and not search_results and not finished_results):
    st.caption("No local match. Search approved webpages for temporary results.")
    if st.button("Search web", key="search_web", disabled=web_cache["results"] is not None):
        if web_cache["results"] is None:
            with st.spinner("Searching approved webpages…"):
                web_cache["results"] = search_web(memes, web_query)
    if web_cache["results"] is not None:
        search_results = web_cache["results"]
        if not search_results:
            st.info("No matching web results available from approved sources.")
results = filter_memes(search_results, categories, emotions)
account = current_account(st.session_state)
view = st.session_state.get("library_view", "home")
saved_ids = []
library_error = None
if account is not None:
    try:
        saved_ids = fetch_library(st.session_state)
    except LibraryError as error:
        library_error = str(error)
if view != "home":
    if account is None:
        results = []
        st.info("Please sign in using Account in the sidebar to use your library.")
    else:
        try:
            ids = fetch_library(st.session_state, recent=True) if view == "recent" else saved_ids
            results = resolve_memes(memes, ids)
        except LibraryError as error:
            library_error = str(error)
            results = []
if library_error:
    st.warning(library_error)
notice = st.session_state.pop("library_notice", None)
if notice:
    st.info(notice)
st.divider()
st.subheader(("Recently Viewed" if view == "recent" else "Saved Memes") if view != "home"
             else (f"Results for '{query.strip()}'" if query.strip() else "Browse Memes"))
if view == "home":
    render_finished_memes(finished_results)
    if results:
        st.subheader("Templates")
if results or not finished_results:
    st.caption(f"{len(results)} template{'s' if len(results) != 1 else ''}"
               + (" matching your filters" if view == "home" and (categories or emotions) else ""))
if view == "home" and finished_results and (categories or emotions):
    st.caption("Category and emotion filters apply to templates.")

if not results:
    if view != "home":
        if account is not None and not library_error:
            st.info("No recently viewed memes yet. Open a meme's details to get started."
                    if view == "recent" else "No saved memes yet. Save a meme to find it here.")
    elif search_results and (categories or emotions):
        st.info("No templates match these filters. Remove a category or emotion to widen your results.")
    elif not finished_results:
        st.info("No meme matched that description. Try describing the scene, emotion, situation, or meme name.")
elif view == "home" and not query.strip() and not categories and not emotions:
    st.caption("Familiar favorites from the collection")

page_key = "page" if view == "home" else "library_page"
st.session_state.setdefault(page_key, 0)
page_count = max(1, (len(results) + PAGE_SIZE - 1) // PAGE_SIZE)
st.session_state[page_key] = min(st.session_state[page_key], page_count - 1)
start = st.session_state[page_key] * PAGE_SIZE
visible_results = results[start:start + PAGE_SIZE]

with st.container(key="results"):
    for row_start in range(0, len(visible_results), 3):
        for column, meme in zip(st.columns(3, gap="medium"),
                                visible_results[row_start:row_start + 3]):
            with column:
                with st.container(key="card-" + meme["id"]):
                    with st.container(key="preview-" + meme["id"]):
                        preview = None
                        try:
                            if meme.get("external_result"):
                                preview = load_external_preview(meme.get("image_url"))
                            elif meme.get("web_result"):
                                # Never refetch an untrusted URL through the catalog preview loader.
                                preview = meme.get("_web_preview")
                            elif meme.get("local_image"):
                                preview = load_local_preview(meme.get("local_image"))
                            else:
                                preview = load_preview(meme.get("image_url"))
                        except Exception:
                            pass

                        if preview is None:
                            st.caption("Preview unavailable")
                        else:
                            try:
                                st.image(BytesIO(preview), use_container_width=True)
                            except Exception:
                                # A corrupt preview must never hide the template details.
                                st.caption("Preview unavailable")

                    st.subheader(meme["name"])
                    if meme.get("web_result") or meme.get("external_result"):
                        st.caption(("External template · " + meme["provider"] + " · Not curated")
                                   if meme.get("external_result") else "Temporary web result · Not in the catalog")
                        if meme.get("source_page"):
                            st.link_button("Source page", meme["source_page"])

                    with st.container(key="meaning-" + meme["id"]):
                        st.write(meme["meaning"])

                    tags = [(tag, "") for tag in meme.get("categories", [])[:2]]
                    tags += [(tag, "emotion") for tag in meme.get("emotions", [])[:1]]

                    st.html(
                        '<div class="mf-tags">' +
                        ''.join(
                            f'<span class="mf-tag {kind}">{escape(tag)}</span>'
                            for tag, kind in tags
                        ) +
                        '</div>'
                    )

                    render_result_actions(preview, "template-" + meme["id"], template=meme)
                    if not (meme.get("web_result") or meme.get("external_result")) and card_actions(meme, saved_ids):
                        st.caption(
                            "Categories: " +
                            ", ".join(meme.get("categories", []))
                        )
                        st.caption(
                            "Emotions: " +
                            ", ".join(meme.get("emotions", []))
                        )

                        if meme.get("aliases"):
                            st.caption(
                                "Also known as: " +
                                ", ".join(meme["aliases"])
                            )

                        if meme.get("situations"):
                            st.markdown("**Common situations**")
                            st.markdown(
                                "\n".join(
                                    "- " + value
                                    for value in meme["situations"]
                                )
                            )

                        st.write(meme["description"])
                        st.caption(
                            "Keywords: " +
                            ", ".join(meme["keywords"])
                        )
            
                        
                    

if results:
    st.caption(f"Showing {start + 1}-{min(start + PAGE_SIZE, len(results))} of {len(results)}")
if page_count > 1:
    previous, page_label, following = st.columns([1, 2, 1])
    with previous:
        st.button("Previous", icon=":material/chevron_left:", key="previous",
                  on_click=turn_page, args=(-1,), disabled=st.session_state[page_key] == 0)
    with page_label:
        st.caption(f"Page {st.session_state[page_key] + 1} of {page_count}")
    with following:
        st.button("Next", icon=":material/chevron_right:", key="next",
                  on_click=turn_page, args=(1,), disabled=st.session_state[page_key] >= page_count - 1)

st.divider()
st.subheader("Explore by Emotion")
st.caption("Find memes for how you feel")
emotion_options = filter_options(memes, "emotions")
quick_emotions = [tag for tag in ["joy", "stress", "confusion", "sadness", "anger", "surprise", "boredom"]
                  if tag in emotion_options]
st.pills("Explore emotions", quick_emotions, key="quick_emotion",
         on_change=quick_emotion_changed, format_func=str.title,
         label_visibility="collapsed")

if view == "home":
    render_intelligence(memes)

# Render after search widgets to preserve their ordering and existing callbacks.
render_account()
