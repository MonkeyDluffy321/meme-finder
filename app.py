"""Meme Finder: searchable template collection with remote previews."""

import json
from html import escape
from io import BytesIO
from pathlib import Path

import streamlit as st

from utils.filters import filter_memes, filter_options
from utils.images import load_preview
from utils.search import search_memes


DATA_PATH = Path(__file__).parent / "data" / "memes.json"
PAGE_SIZE = 6

st.set_page_config(page_title="Meme Finder", page_icon=":material/image_search:", layout="wide")

st.html("<style>" + Path(__file__).with_name("ui.css").read_text(encoding="utf-8") + "</style>")


def reset_page():
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
    clear_search()
    reset_filters()


def turn_page(offset):
    st.session_state.page += offset


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
except (OSError, json.JSONDecodeError):
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
                  type="primary", use_container_width=True, key="home")
        for label, icon in [("Explore", "explore"), ("Categories", "category"),
                            ("Saved", "bookmark"), ("Recently Viewed", "history")]:
            st.button(label, icon=f":material/{icon}:", disabled=True,
                      help="Not available in this prototype", use_container_width=True)
    with st.container(key="product_info"):
        st.divider()
        st.caption("Meme Finder V2")
        st.caption(f"{len(memes)} templates in the collection")
        st.caption("Local discovery. No account needed.")
        st.caption("Previews hosted by Imgflip.")

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

search_results = search_memes(memes, query)
results = filter_memes(search_results, categories, emotions)
st.divider()
st.subheader(f"Results for '{query.strip()}'" if query.strip() else "Browse Memes")
st.caption(f"{len(results)} template{'s' if len(results) != 1 else ''}"
           + (" matching your filters" if categories or emotions else ""))

if not results:
    if search_results and (categories or emotions):
        st.info("No templates match these filters. Remove a category or emotion to widen your results.")
    else:
        st.info("No meme matched that description. Try describing the scene, emotion, situation, or meme name.")
elif not query.strip() and not categories and not emotions:
    st.caption("Familiar favorites from the collection")

page_count = max(1, (len(results) + PAGE_SIZE - 1) // PAGE_SIZE)
st.session_state.page = min(st.session_state.page, page_count - 1)
start = st.session_state.page * PAGE_SIZE
visible_results = results[start:start + PAGE_SIZE]

with st.container(key="results"):
    for row_start in range(0, len(visible_results), 3):
        for column, meme in zip(st.columns(3, gap="medium"),
                                visible_results[row_start:row_start + 3]):
            with column:
                with st.container(key="card-" + meme["id"]):
                    with st.container(key="preview-" + meme["id"]):
                        preview = load_preview(meme.get("image_url"))
                        if preview is None:
                            st.caption("Preview unavailable")
                        else:
                            try:
                                st.image(BytesIO(preview), use_container_width=True)
                            except Exception:
                                # A corrupt remote preview must never hide the template details.
                                st.caption("Preview unavailable")
                    st.subheader(meme["name"])
                    with st.container(key="meaning-" + meme["id"]):
                        st.write(meme["meaning"])
                    tags = [(tag, "") for tag in meme.get("categories", [])[:2]]
                    tags += [(tag, "emotion") for tag in meme.get("emotions", [])[:1]]
                    st.html('<div class="mf-tags">' + ''.join(
                        f'<span class="mf-tag {kind}">{escape(tag)}</span>'
                        for tag, kind in tags) + '</div>')
                    with st.expander("More details", expanded=False):
                        st.caption("Categories: " + ", ".join(meme.get("categories", [])))
                        st.caption("Emotions: " + ", ".join(meme.get("emotions", [])))
                        if meme.get("aliases"):
                            st.caption("Also known as: " + ", ".join(meme["aliases"]))
                        if meme.get("situations"):
                            st.markdown("**Common situations**")
                            st.markdown("\n".join("- " + value for value in meme["situations"]))
                        st.write(meme["description"])
                        st.caption("Keywords: " + ", ".join(meme["keywords"]))

if results:
    st.caption(f"Showing {start + 1}-{min(start + PAGE_SIZE, len(results))} of {len(results)}")
if page_count > 1:
    previous, page_label, following = st.columns([1, 2, 1])
    with previous:
        st.button("Previous", icon=":material/chevron_left:", key="previous",
                  on_click=turn_page, args=(-1,), disabled=st.session_state.page == 0)
    with page_label:
        st.caption(f"Page {st.session_state.page + 1} of {page_count}")
    with following:
        st.button("Next", icon=":material/chevron_right:", key="next",
                  on_click=turn_page, args=(1,), disabled=st.session_state.page >= page_count - 1)

st.divider()
st.subheader("Explore by Emotion")
st.caption("Find memes for how you feel")
emotion_options = filter_options(memes, "emotions")
quick_emotions = [tag for tag in ["joy", "stress", "confusion", "sadness", "anger", "surprise", "boredom"]
                  if tag in emotion_options]
st.pills("Explore emotions", quick_emotions, key="quick_emotion",
         on_change=quick_emotion_changed, format_func=str.title,
         label_visibility="collapsed")
