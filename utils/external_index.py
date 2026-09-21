"""Read-only search of external template metadata, separate from the catalog."""

from copy import deepcopy
from functools import lru_cache
from hashlib import sha256
from ipaddress import ip_address
import json
from pathlib import Path
from urllib.parse import urlsplit

from utils.crawler import normalize_url
from utils.importer_url import _safe_public_ip
from utils.search import normalized_words, search_memes


INDEX_PATH = Path(__file__).resolve().parents[1] / "data" / "external_templates.json"
MAX_RECORDS = 10000
MAX_INDEX_BYTES = 8 * 1024 * 1024


def public_metadata_url(value):
    """Validate syntax/literal addresses without network access during search.

    DNS and every redirect are validated by the safe preview downloader later.
    """
    if not isinstance(value, str) or len(value) > 2048:
        return None
    url = normalize_url(value)
    if not url:
        return None
    host = urlsplit(url).hostname
    if host == "localhost" or host.endswith((".localhost", ".local")) or "%" in host:
        return None
    try:
        return url if _safe_public_ip(ip_address(host)) else None
    except ValueError:
        return url if "." in host else None


def normalize_record(row):
    if not isinstance(row, dict):
        return None
    fields = ("name", "provider", "template_id")
    if any(not isinstance(row.get(key), str) or not row[key].strip()
           or len(row[key]) > 200 for key in fields):
        return None
    aliases = row.get("aliases", [])
    if (not isinstance(aliases, list) or len(aliases) > 32
            or any(not isinstance(alias, str) or not alias.strip() or len(alias) > 200 for alias in aliases)):
        return None
    image = public_metadata_url(row.get("image_url"))
    source = public_metadata_url(row.get("source_page")) if row.get("source_page") else None
    if not image or (row.get("source_page") and not source):
        return None
    result = {key: " ".join(row[key].split()) for key in fields}
    result["provider"] = result["provider"].casefold()
    unique = {}
    for alias in aliases:
        alias = " ".join(alias.split())
        unique.setdefault(alias.casefold(), alias)
    result.update(aliases=list(unique.values()), image_url=image, source_page=source)
    return result


def clean_records(rows):
    """Skip malformed rows; merge duplicate IDs/images while preserving aliases."""
    result, identities, images = [], {}, {}
    for raw in rows:
        row = normalize_record(raw)
        if row is None:
            continue
        key = (row["provider"], row["template_id"])
        existing = identities.get(key)
        if existing is None:
            existing = images.get(row["image_url"])
        if existing is not None:
            merged = dict.fromkeys(existing["aliases"] + [row["name"]] + row["aliases"])
            existing["aliases"] = list(merged)[:32]
            identities[key] = existing
            images[row["image_url"]] = existing
            continue
        identities[key] = images[row["image_url"]] = row
        result.append(row)
    return result


def read_index(path=INDEX_PATH):
    with Path(path).open("rb") as handle:
        raw = handle.read(MAX_INDEX_BYTES + 1)
    if len(raw) > MAX_INDEX_BYTES:
        raise ValueError("External index exceeds byte limit.")
    data = json.loads(raw)
    if (not isinstance(data, dict) or data.get("version") != 1
            or not isinstance(data.get("records"), list) or len(data["records"]) > MAX_RECORDS):
        raise ValueError("Expected external index version 1 and bounded records list.")
    return data


@lru_cache(maxsize=4)
def _load(path, modified, size):
    records = clean_records(read_index(path)["records"])
    exact = {}
    for row in records:
        identity = sha256(json.dumps([row["provider"], row["template_id"]]).encode()).hexdigest()
        row.update(id="external-" + identity, external_result=True, meaning="", description="")
        for label in (row["name"], *row["aliases"]):
            key = tuple(normalized_words(label))
            bucket = exact.setdefault(key, [])
            if row not in bucket:
                bucket.append(row)
    return records, exact


def search_external_templates(query, *, index_path=INDEX_PATH):
    """No network/writes. Reuse V1 lexical/fuzzy ranking for identity metadata."""
    if not query.strip():
        return []
    try:
        path = Path(index_path).resolve()
        stat = path.stat()
        records, exact = _load(str(path), stat.st_mtime_ns, stat.st_size)
        pool = exact.get(tuple(normalized_words(query)), records)
        return deepcopy(search_memes(pool, query, use_semantic=False))
    except (OSError, ValueError, TypeError):
        return []
