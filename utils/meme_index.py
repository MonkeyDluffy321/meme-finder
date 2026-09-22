"""Provider-independent finished meme data. No fetching or template ranking."""

from hashlib import sha256
from itertools import islice
import json
from pathlib import Path
import re
from typing import Iterable, Mapping, Protocol
import unicodedata

from utils.external_index import public_metadata_url
from utils.uploads import validate_upload
from utils.template_index import image_hash, informative


INDEX_PATH = Path(__file__).resolve().parents[1] / "data" / "meme_instances.json"
MAX_RECORDS = 10000
MAX_INDEX_BYTES = 8 * 1024 * 1024


class MemeProvider(Protocol):
    """Adapters supply records from approved sources; this layer never crawls."""

    def records(self) -> Iterable[Mapping]: ...


def normalize_caption(text):
    # Keep punctuation, numbers and words: differences can change the joke.
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def image_fingerprints(content):
    """Explicit local byte input only. Reuse bounded image validation and hashes."""
    upload = validate_upload(content)
    image = upload.image
    pixels = str(image.size).encode() + image.mode.encode() + image.tobytes()
    result = {"image_sha256": upload.digest, "pixel_sha256": sha256(pixels).hexdigest()}
    if informative(image):
        result["perceptual_hash"] = image_hash(image)
    return result


def normalize_record(raw):
    if not isinstance(raw, Mapping):
        return None
    row = {}
    for key, limit in (("meme_id", 200), ("provider", 200), ("caption_text", 5000),
                       ("template_id", 200), ("template_name", 200),
                       ("situation", 1000), ("language", 40)):
        value = raw.get(key, "")
        if value is None and key in ("template_id", "template_name"):
            value = ""
        if not isinstance(value, str) or len(value) > limit:
            return None
        row[key] = value.strip()
    if not row["meme_id"] or not row["provider"]:
        return None
    row["provider"] = row["provider"].casefold()
    row["language"] = row["language"].casefold() or "und"
    row["normalized_caption"] = normalize_caption(row["caption_text"])
    for key in ("image_url", "source_page"):
        value = raw.get(key)
        row[key] = public_metadata_url(value) if value else None
        if (value and not row[key]) or (key == "image_url" and not row[key]):
            return None
    topics = raw.get("topics", [])
    if not isinstance(topics, list) or len(topics) > 32:
        return None
    if any(not isinstance(topic, str) or len(topic) > 200 for topic in topics):
        return None
    row["topics"] = list(dict.fromkeys(normalize_caption(topic) for topic in topics if topic.strip()))
    for key, pattern in (("image_sha256", r"[a-fA-F0-9]{64}"),
                         ("pixel_sha256", r"[a-fA-F0-9]{64}"),
                         ("perceptual_hash", r"[01]{256}")):
        value = raw.get(key)
        if value is not None:
            if not isinstance(value, str) or not re.fullmatch(pattern, value):
                return None
            row[key] = value.lower()
    # Confidence concerns source provenance, never an inferred identity score.
    confidence = raw.get("source_confidence", "unknown")
    if confidence not in ("unknown", "reported", "verified"):
        return None
    row["source_confidence"] = confidence
    row["kind"] = "finished_meme"
    row["instance_key"] = sha256(json.dumps([row["provider"], row["meme_id"],
                                            row["image_url"], row["normalized_caption"]]).encode()).hexdigest()
    return row


def clean_records(records):
    """Collapse exact image evidence only; retain possible perceptual copies.

    Provider IDs, template IDs and caption equality alone never merge records.
    Hashes must come from trusted ingestion, not unverified provider assertions.
    """
    result, exact, perceptual = [], {}, {}
    try:
        records = iter(records)
    except TypeError:
        return []
    for raw in islice(records, MAX_RECORDS):
        row = normalize_record(raw)
        if row is None:
            continue
        reference = {key: row[key] for key in ("provider", "meme_id", "image_url", "source_page", "source_confidence")}
        keys = [(key, row[key]) for key in ("image_sha256", "pixel_sha256") if key in row]
        if not keys:
            keys.append(("locator", row["image_url"], row["normalized_caption"]))
        existing = next((exact[key] for key in keys if key in exact), None)
        if existing is not None:
            if reference not in existing["provenance"]:
                existing["provenance"].append(reference)
            # Retain alternate OCR/transcriptions rather than silently discarding them.
            if row["caption_text"] not in existing["caption_variants"]:
                existing["caption_variants"].append(row["caption_text"])
        else:
            row["provenance"] = [reference]
            row["caption_variants"] = [row["caption_text"]]
            key = (row.get("perceptual_hash"), row["normalized_caption"])
            if all(key):
                if key in perceptual:
                    row["possible_duplicate_of"] = perceptual[key]["instance_key"]
                else:
                    perceptual[key] = row
            existing = row
            result.append(row)
        for key in keys:
            exact[key] = existing
    return result


def load_index(path=INDEX_PATH):
    """Fail closed on corrupt/oversized files; skip malformed individual rows."""
    try:
        with Path(path).open("rb") as handle:
            content = handle.read(MAX_INDEX_BYTES + 1)
        if len(content) > MAX_INDEX_BYTES:
            return []
        data = json.loads(content)
        if (not isinstance(data, dict) or type(data.get("version")) is not int or data["version"] != 1
                or not isinstance(data.get("records"), list) or len(data["records"]) > MAX_RECORDS):
            return []
        return clean_records(data["records"])
    except (OSError, ValueError, TypeError, RecursionError):
        return []
