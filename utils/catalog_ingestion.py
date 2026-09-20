"""Explicitly approved candidate ingestion; no UI or candidate-queue mutation."""

from hashlib import sha256
from pathlib import Path

from utils.crawler import catalog_hashes, normalize_url, NEAR_DUPLICATE_BITS
from utils.importer import (DATA_DIR, LIST_FIELDS, DuplicateError, ImportError,
                            _read_records, import_meme, prepare_record)
from utils.importer_url import download_image
from utils.template_index import image_hash, informative
from utils.uploads import UploadError, validate_upload


def _final_duplicate(records, upload, root):
    hashes, exact = catalog_hashes(records, image_dir=root / "imported_images")
    duplicate = exact.get(sha256(upload.preview).hexdigest())
    if duplicate or not informative(upload.image):
        return duplicate
    fingerprint = image_hash(upload.image)
    return next((identity for other, identity in hashes
                 if sum(a != b for a, b in zip(fingerprint, other)) <= NEAR_DUPLICATE_BITS), None)


def ingest_candidate(candidate, *, approved=False, data_dir=None):
    """Return status/id/message. Only literal approved=True authorizes ingestion.

    The caller authenticates the approver. data_dir is trusted backend config.
    A supplied crawler digest binds approval to the sanitized image reviewed.
    """
    identity = None

    def result(status, message, record_id=None):
        return {"status": status, "id": record_id or identity, "message": message}

    if approved is not True:
        return result("rejected", "Explicit approval is required.")
    try:
        if not isinstance(candidate, dict):
            raise ImportError("Candidate must be an object.")
        provenance = {}
        for field in ("source_page", "source_image_url"):
            url = normalize_url(candidate.get(field))
            if not url:
                raise ImportError(f"{field} must be a valid HTTP/HTTPS URL.")
            provenance[field] = url
        metadata = {field: candidate.get(field) for field in ("name", "meaning")}
        for field in LIST_FIELDS:
            values = candidate.get(field, [] if field == "aliases" else None)
            if not isinstance(values, list) or any(not isinstance(v, str) or not v.strip() for v in values):
                raise ImportError(f"{field} must be a list of nonblank strings.")
            metadata[field] = ", ".join(values)
        identity = prepare_record(metadata)["id"]
        if candidate.get("duplicate_status") == "duplicate":
            return result("duplicate", "Candidate was marked as a duplicate.")
    except (ImportError, TypeError, ValueError) as error:
        return result("rejected", str(error))

    root = Path(data_dir) if data_dir is not None else DATA_DIR
    try:
        # Cheap preflight avoids downloading known IDs. The locked check below
        # is authoritative if another importer writes during the download.
        records = _read_records(root / "memes.json") + _read_records(root / "imported_memes.json", optional=True)
        if any(record["id"] == identity for record in records):
            return result("duplicate", "Meme ID already exists.")
        content = download_image(provenance["source_image_url"], respect_indexing=True)
        upload = validate_upload(content)
        if candidate.get("content_sha256") and candidate["content_sha256"] != sha256(upload.preview).hexdigest():
            return result("rejected", "Source image changed since review. Crawl and approve it again.")
        record = import_meme(metadata, content, data_dir=root, duplicate_check=_final_duplicate,
                             provenance=provenance)
        return result("imported", "Approved meme added to the catalog.", record["id"])
    except DuplicateError as error:
        return result("duplicate", str(error), error.identity)
    except UploadError as error:
        return result("rejected", str(error))
    except Exception:
        return result("error", "Ingestion failed. Check the source, catalog, and storage permissions.")
