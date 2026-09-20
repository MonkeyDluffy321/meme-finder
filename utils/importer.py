"""Validated local imports with atomic JSON persistence and image rollback."""

import json
import os
from pathlib import Path
import re
import tempfile
import unicodedata
from uuid import uuid4

from utils.uploads import UploadError, validate_upload


DATA_DIR = Path(__file__).resolve().parents[1] / "data"
LIST_FIELDS = ("keywords", "situations", "emotions", "categories", "aliases")


class ImportError(ValueError):
    """An importer error suitable for display to the user."""


def meme_id(name):
    text = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:100].rstrip("-")
    if not slug:
        raise ImportError("Name must contain at least one letter A–Z or digit.")
    return slug


def normalize_list(text):
    values, seen = [], set()
    for part in text.split(","):
        value = " ".join(part.split())
        if value and value.casefold() not in seen:
            values.append(value)
            seen.add(value.casefold())
    return values


def _read_records(path, optional=False):
    try:
        records = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        if optional:
            return []
        raise ImportError(f"Could not read {path.name}.") from None
    except (OSError, ValueError):
        raise ImportError(f"Could not read {path.name}: expected a valid JSON list.") from None
    if not isinstance(records, list):
        raise ImportError(f"Invalid {path.name}: expected a JSON list.")
    ids = set()
    for record in records:
        if (not isinstance(record, dict)
                or any(not isinstance(record.get(key), str) or not record[key].strip()
                       for key in ("id", "name", "meaning", "description"))
                or any(not isinstance(record.get(key), list)
                       or any(not isinstance(v, str) or not v.strip() for v in record[key])
                       for key in LIST_FIELDS)):
            raise ImportError(f"Invalid meme record in {path.name}.")
        if record["id"] in ids:
            raise ImportError(f"Duplicate ID in {path.name}: {record['id']}.")
        ids.add(record["id"])
    return records


def _write_records(path, records):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=".import-", suffix=".tmp", delete=False) as handle:
            temporary = Path(handle.name)
            json.dump(records, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def import_meme(metadata, content, *, data_dir=None):
    """Import bytes; data_dir is trusted application configuration, never user input."""
    record = {}
    for field in ("name", "meaning"):
        value = metadata.get(field, "")
        if not isinstance(value, str) or not value.strip():
            raise ImportError(f"{field.title()} is required.")
        record[field] = " ".join(value.split())
    record["id"] = meme_id(record["name"])
    record["description"] = record["meaning"]
    for field in LIST_FIELDS:
        value = metadata.get(field, "")
        if not isinstance(value, str):
            raise ImportError(f"{field.title()} must be comma-separated text.")
        record[field] = normalize_list(value)
        if field != "aliases" and not record[field]:
            raise ImportError(f"{field.title()} is required.")
    try:
        upload = validate_upload(content)
    except UploadError as error:
        raise ImportError(str(error)) from None
    # Keep normalized files within the existing local preview reader's 5 MB limit.
    if len(upload.preview) > 5 * 1024 * 1024:
        raise ImportError("Normalized image exceeds the 5 MB preview limit. Use a smaller image.")

    root = Path(data_dir) if data_dir is not None else DATA_DIR
    image_dir = root / "imported_images"
    if image_dir.is_symlink() or image_dir.resolve().parent != root.resolve():
        raise ImportError("Imported image directory must be inside the data directory.")
    target = root / "imported_memes.json"
    lock = root / ".meme-import.lock"
    try:
        lock_handle = lock.open("x")
    except FileExistsError:
        raise ImportError("Another import is in progress. Please try again shortly.") from None
    except OSError:
        raise ImportError("Could not access the importer data directory.") from None
    image_path = None
    try:
        with lock_handle:
            main = _read_records(root / "memes.json")
            imported = _read_records(target, optional=True)
            if any(meme["id"] == record["id"] for meme in main + imported):
                raise ImportError(f"Meme ID '{record['id']}' already exists. Choose another name.")
            image_dir.mkdir(exist_ok=True)
            record["local_image"] = f"{record['id']}-{uuid4().hex}.png"
            candidate = image_dir / record["local_image"]
            with candidate.open("xb") as handle:
                image_path = candidate
                handle.write(upload.preview)
                handle.flush()
                os.fsync(handle.fileno())
            _write_records(target, imported + [record])
        return record
    except Exception as error:
        if image_path is not None:
            image_path.unlink(missing_ok=True)
        if isinstance(error, ImportError):
            raise
        raise ImportError("Could not save the import. Please check disk space and permissions.") from error
    finally:
        lock.unlink(missing_ok=True)
