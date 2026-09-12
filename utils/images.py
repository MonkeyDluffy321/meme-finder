"""Small, memory-only cache for remote template previews."""

from http.client import HTTPException
from urllib.request import Request, urlopen

import streamlit as st


MAX_IMAGE_BYTES = 5 * 1024 * 1024


@st.cache_data(ttl=300, max_entries=64, show_spinner=False)
def load_preview(url):
    """Return remote image bytes or None; failures are briefly cached too."""
    if not isinstance(url, str) or not url.startswith(("http://", "https://")):
        return None
    try:
        request = Request(url, headers={"User-Agent": "MemeFinder/2.0"})
        with urlopen(request, timeout=3) as response:
            if not response.headers.get_content_type().startswith("image/"):
                return None
            content = response.read(MAX_IMAGE_BYTES + 1)
        return content if 0 < len(content) <= MAX_IMAGE_BYTES else None
    except (OSError, ValueError, HTTPException):
        return None
