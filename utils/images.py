"""Small, memory-only cache for remote template previews."""

from http.client import HTTPException
from pathlib import Path
from urllib.request import Request, urlopen

import streamlit as st

from utils.importer_url import download_image
from utils.uploads import validate_upload


MAX_IMAGE_BYTES = 5 * 1024 * 1024
IMPORTED_IMAGE_DIR = Path(__file__).resolve().parents[1] / "data" / "imported_images"


@st.cache_data(ttl=300, max_entries=64, show_spinner=False)
def load_external_preview(url):
    """Untrusted external-index images use the existing safe transport/validator."""
    try:
        return validate_upload(download_image(url, respect_indexing=True)).preview
    except (OSError, ValueError, HTTPException):
        return None


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
@st.cache_data(ttl=300, max_entries=64, show_spinner=False)
def load_local_preview(filename):
    """Load a bounded image only from data/imported_images."""
    if not isinstance(filename, str) or not filename.strip():
        return None

    if Path(filename).name != filename:
        return None

    path = IMPORTED_IMAGE_DIR / filename

    try:
        content = path.read_bytes()

        if not content or len(content) > MAX_IMAGE_BYTES:
            return None

        return content
    except OSError:
        return None
