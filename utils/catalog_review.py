"""Durable internal review queue, independent of catalog and UI state."""

from contextlib import contextmanager
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

from utils.catalog_ingestion import ingest_candidate
from utils.importer import LIST_FIELDS, _write_records


QUEUE_PATH = Path(__file__).resolve().parents[1] / "data" / "catalog_review.json"
STATUSES = {"pending", "imported", "duplicate", "rejected", "error"}
EDITABLE = {"name", "meaning", *LIST_FIELDS}


class ReviewError(ValueError):
    pass


class ReviewQueue:
    def __init__(self, path=QUEUE_PATH, *, data_dir=None):
        self.path = Path(path)
        self.data_dir = data_dir

    def entries(self, status=None):
        try:
            rows = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return []
        except (OSError, ValueError) as error:
            raise ReviewError("Could not read the review queue.") from error
        if (not isinstance(rows, list) or any(
                not isinstance(row, dict) or not isinstance(row.get("queue_id"), str)
                or row.get("status") not in STATUSES or not isinstance(row.get("candidate"), dict)
                for row in rows) or len({row["queue_id"] for row in rows}) != len(rows)):
            raise ReviewError("Invalid review queue; no changes made.")
        return [row for row in rows if status is None or row["status"] == status]

    @contextmanager
    def _locked(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lock = self.path.with_suffix(self.path.suffix + ".lock")
        try:
            handle = lock.open("x")
        except FileExistsError:
            raise ReviewError("Review queue is busy. Retry shortly.") from None
        try:
            with handle:
                yield
        finally:
            lock.unlink(missing_ok=True)

    def enqueue(self, candidates):
        """Accept crawl(...)[\"candidates\"]; repeated sources retain their status."""
        with self._locked():
            rows = self.entries()
            known = {row["queue_id"] for row in rows}
            image_urls = {row["candidate"].get("source_image_url") for row in rows}
            digests = {row["candidate"].get("content_sha256") for row in rows}
            added = []
            for candidate in candidates:
                if not isinstance(candidate, dict) or not all(
                        isinstance(candidate.get(field), str) and candidate[field].strip()
                        for field in ("source_page", "source_image_url")):
                    raise ReviewError("Candidate source URLs are required.")
                identity = sha256(json.dumps([candidate["source_page"], candidate["source_image_url"],
                                             candidate.get("content_sha256", "")]).encode()).hexdigest()
                digest = candidate.get("content_sha256")
                if (identity not in known and candidate["source_image_url"] not in image_urls
                        and (not digest or digest not in digests)):
                    rows.append({"queue_id": identity, "candidate": deepcopy(candidate),
                                 "status": "pending", "result": None})
                    known.add(identity)
                    image_urls.add(candidate["source_image_url"])
                    digests.add(digest)
                    added.append(identity)
            _write_records(self.path, rows)
            return added

    def _find(self, rows, identity):
        row = next((row for row in rows if row["queue_id"] == identity), None)
        if row is None:
            raise ReviewError("Unknown queue candidate.")
        return row

    def approve(self, identity, edits=None):
        with self._locked():
            rows = self.entries()
            row = self._find(rows, identity)
            if row["status"] != "pending":
                raise ReviewError("Only pending candidates can be approved. Errors require explicit retry.")
            candidate = deepcopy(row["candidate"])
            if edits is not None:
                if not isinstance(edits, dict) or set(edits) - EDITABLE:
                    raise ReviewError("Only metadata fields can be edited.")
                candidate.update(deepcopy(edits))
            row["candidate"] = candidate
            # Persist the attempt BEFORE ingestion. A crash cannot silently put
            # an approved candidate back into the normal pending view.
            row["status"] = "error"
            row["result"] = {"status": "error", "id": None,
                             "message": "Approval interrupted. Check catalog before retrying."}
            _write_records(self.path, rows)
            try:
                result = ingest_candidate(deepcopy(candidate), approved=True, data_dir=self.data_dir)
                if not isinstance(result, dict) or result.get("status") not in STATUSES - {"pending"}:
                    raise ReviewError("Invalid ingestion result.")
            except Exception:
                result = {"status": "error", "id": None, "message": "Ingestion failed; explicit retry is available."}
            row["status"], row["result"] = result["status"], result
            _write_records(self.path, rows)
            return deepcopy(result)

    def reject(self, identity):
        with self._locked():
            rows = self.entries()
            row = self._find(rows, identity)
            if row["status"] not in {"pending", "error"}:
                raise ReviewError("Candidate is already resolved.")
            row["status"] = "rejected"
            row["result"] = {"status": "rejected", "id": None, "message": "Rejected by reviewer."}
            _write_records(self.path, rows)
            return deepcopy(row["result"])

    def retry(self, identity):
        with self._locked():
            rows = self.entries()
            row = self._find(rows, identity)
            if row["status"] != "error":
                raise ReviewError("Only errors can be retried.")
            row["status"] = "pending"
            _write_records(self.path, rows)
