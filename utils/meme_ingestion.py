"""Offline finished-meme provider -> normalization -> validation -> index service.

Adapters implement meme_index.MemeProvider.records(). They may expose a name
as the default provider. No URLs are fetched here; image_bytes is optional local
input for trusted fingerprints. Provider-supplied fingerprint claims are ignored.
"""

from collections.abc import Iterable, Mapping
from hashlib import sha256
from itertools import islice
import json
import os
from pathlib import Path

from utils.importer import _write_records
from utils.meme_index import (INDEX_PATH, MAX_INDEX_BYTES, MAX_RECORDS, MemeProvider,
                              clean_records, image_fingerprints, normalize_record)


ALIASES = {
    "meme_id": ("external_id", "id"),
    "provider": ("source",),
    "caption_text": ("caption", "text"),
    "topics": ("tags",),
    "situation": ("description",),
}


def normalize_provider_record(raw, provider=None):
    """Map common export fields into the one existing V4 schema.

    Canonical fields take precedence. Custom/nested exports should be mapped by
    the adapter. External IDs become meme_id; absent IDs get a stable local ID.
    Popularity/unknown fields do not affect the index or ranking.
    """
    if not isinstance(raw, Mapping):
        return None
    row = dict(raw)
    for field, aliases in ALIASES.items():
        if field not in row:
            for alias in aliases:
                if alias in raw:
                    row[field] = raw[alias]
                    break
    row.setdefault("provider", provider)
    if type(row.get("meme_id")) is int:
        row["meme_id"] = str(row["meme_id"])
    for field in ("image_url", "source_page"):
        if field in row and row[field] is not None and not isinstance(row[field], str):
            return None
    for field in ("image_sha256", "pixel_sha256", "perceptual_hash"):
        row.pop(field, None)
    if "image_bytes" in raw:
        if not isinstance(raw["image_bytes"], bytes):
            return None
        row.update(image_fingerprints(raw["image_bytes"]))
    if "meme_id" not in row or row["meme_id"] is None:
        # Validate every other field before deriving an identity from it.
        row["meme_id"] = "generated"
        normalized = normalize_record(row)
        if normalized is None:
            return None
        identity = [normalized.get(key) for key in
                    ("provider", "source_page", "image_url", "normalized_caption", "image_sha256")]
        row["meme_id"] = "generated-" + sha256(_canonical(identity).encode()).hexdigest()
    return normalize_record(row)


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _read_existing(path):
    if not path.exists():
        return []
    with path.open("rb") as handle:
        content = handle.read(MAX_INDEX_BYTES + 1)
    if len(content) > MAX_INDEX_BYTES:
        raise ValueError("Existing index exceeds byte limit; unchanged.")
    data = json.loads(content)
    if (not isinstance(data, dict) or type(data.get("version")) is not int
            or data["version"] != 1 or not isinstance(data.get("records"), list)
            or len(data["records"]) > MAX_RECORDS):
        raise ValueError("Invalid existing index; unchanged.")
    # Never overwrite a corrupt index using the search loader's empty fallback.
    rows = data["records"]
    if any(normalize_record(row) is None for row in rows):
        raise ValueError("Invalid existing record; index unchanged.")
    if any("provenance" in row or "caption_variants" in row for row in rows):
        raise ValueError("Expected source records, not collapsed search results; index unchanged.")
    return [normalize_record(row) for row in rows]


def ingest_memes(providers: MemeProvider | Iterable[MemeProvider], *, index_path=INDEX_PATH):
    """Ingest one MemeProvider or an iterable of providers, independently.

    accepted counts valid inputs (including duplicates); added/duplicates use
    existing V4 collapse rules. errors names provider/record positions without
    leaking provider exception contents. Storage limits or write errors leave disk intact.
    A sibling exclusive lock serializes cooperating writers; stale locks after a
    killed process require manual removal. Search never calls this service.
    """
    if callable(getattr(providers, "records", None)):
        providers = [providers]
    summary = dict(received=0, accepted=0, invalid=0, duplicates=0, added=0,
                   index_size=0, errors=[], written=False)
    incoming = []
    for position, provider in enumerate(providers):
        try:
            for raw in islice(provider.records(), MAX_RECORDS - summary["received"]):
                summary["received"] += 1
                try:
                    row = normalize_provider_record(raw, getattr(provider, "name", None))
                except Exception:
                    row = None
                    summary["errors"].append(f"Provider {position}: record {summary['received']} failed.")
                if row is None:
                    summary["invalid"] += 1
                else:
                    incoming.append(row)
                    summary["accepted"] += 1
            # Conservatively report hitting the bound, without consuming more.
            if summary["received"] >= MAX_RECORDS:
                summary["errors"].append("Import input limit reached; remaining providers skipped.")
                break
        except Exception:
            summary["errors"].append(f"Provider {position}: enumeration failed.")

    path = Path(index_path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = path.with_name(path.name + ".lock")
    # Hold the lock from read through atomic replacement to avoid lost updates.
    handle = lock.open("x")
    try:
        with handle:
            previous = _read_existing(path)
            before = len(clean_records(previous))
            # Keep source rows so clean_records can rebuild all provenance and
            # caption variants on every load. Identical source rows occur once.
            unique = {_canonical(row): row for row in [*previous, *incoming]}
            records = [unique[key] for key in sorted(unique)]
            if len(records) > MAX_RECORDS:
                raise ValueError("Combined index exceeds record limit; unchanged.")
            size = len(clean_records(records))
            summary.update(index_size=size, added=size - before,
                           duplicates=summary["accepted"] - (size - before))
            data = {"version": 1, "records": records}
            serialized = (json.dumps(data, ensure_ascii=False, indent=2) + "\n").replace("\n", os.linesep)
            if len(serialized.encode("utf-8")) > MAX_INDEX_BYTES:
                raise ValueError("Combined index exceeds byte limit; unchanged.")
            if incoming and records != previous:
                _write_records(path, data)
                summary["written"] = True
    finally:
        lock.unlink()
    return summary
