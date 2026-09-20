from copy import deepcopy
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

from utils.catalog_ingestion import ingest_candidate
from utils.importer import import_meme
from utils.search import search_memes


class IngestionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        (self.root / "memes.json").write_text("[]")
        self.target = self.root / "imported_memes.json"
        buffer = BytesIO()
        Image.effect_noise((200, 200), 70).convert("RGB").save(buffer, format="PNG")
        self.content = buffer.getvalue()
        self.candidate = dict(source_page="https://example.com/page", source_image_url="https://example.com/meme",
                              name="Office Celebration", meaning="Celebrating success at work",
                              keywords=["celebration", "work", "work"], situations=["finishing work"],
                              emotions=["joy"], categories=["work"], duplicate_status="not_detected")
        download = patch("utils.catalog_ingestion.download_image", return_value=self.content)
        self.download = download.start()
        self.addCleanup(download.stop)

    def ingest(self, **kwargs):
        return ingest_candidate(self.candidate, approved=True, data_dir=self.root, **kwargs)

    def assert_no_content(self):
        self.assertFalse(self.target.exists())
        images = self.root / "imported_images"
        self.assertFalse(images.exists() and list(images.iterdir()))
        self.assertFalse(list(self.root.glob(".import-*")))
        self.assertFalse((self.root / ".meme-import.lock").exists())

    def test_success_provenance_search_aliases_and_input_unchanged(self):
        before = deepcopy(self.candidate)
        result = self.ingest()
        self.assertEqual(result["status"], "imported")
        self.assertEqual(self.candidate, before)
        records = json.loads(self.target.read_text())
        record = records[0]
        self.assertEqual(record["aliases"], [])
        self.assertEqual(record["source_page"], before["source_page"])
        self.assertEqual(record["source_image_url"], before["source_image_url"])
        self.assertEqual(record["keywords"], ["celebration", "work"])
        self.assertEqual(search_memes(records, "office celebration")[0]["id"], result["id"])
        self.download.assert_called_once_with(before["source_image_url"], respect_indexing=True)
        with Image.open(self.root / "imported_images" / record["local_image"]) as image:
            self.assertEqual(image.format, "PNG")

    def test_unapproved_zero_downloads_or_writes(self):
        for approval in (False, None, "true", 1):
            result = ingest_candidate(self.candidate, approved=approval, data_dir=self.root)
            self.assertEqual(result["status"], "rejected")
        self.download.assert_not_called()
        self.assertEqual([path.name for path in self.root.iterdir()], ["memes.json"])

    def test_missing_required_metadata_before_download(self):
        for field in ("source_page", "source_image_url", "name", "meaning", "keywords", "situations", "emotions", "categories"):
            candidate = deepcopy(self.candidate)
            del candidate[field]
            with self.subTest(field=field):
                result = ingest_candidate(candidate, approved=True, data_dir=self.root)
                self.assertEqual(result["status"], "rejected")
        self.download.assert_not_called()
        self.assert_no_content()

    def test_invalid_metadata_and_urls(self):
        for field, value in (("keywords", "work"), ("emotions", []), ("aliases", [None]),
                             ("source_image_url", "file:///tmp/image"), ("name", "...")):
            with self.subTest(field=field), patch.dict(self.candidate, {field: value}):
                self.assertEqual(self.ingest()["status"], "rejected")
        self.download.assert_not_called()

    def test_duplicate_id_does_not_download_again(self):
        self.assertEqual(self.ingest()["status"], "imported")
        before = self.target.read_bytes()
        self.download.reset_mock()
        self.assertEqual(self.ingest()["status"], "duplicate")
        self.download.assert_not_called()
        self.assertEqual(self.target.read_bytes(), before)

    def test_final_exact_duplicate_with_different_name(self):
        first = self.ingest()
        self.candidate["name"] = "Another name"
        with patch("utils.importer._write_records", side_effect=AssertionError("Must not persist")):
            result = self.ingest()
        self.assertEqual(result["status"], "duplicate")
        self.assertEqual(result["id"], first["id"])
        self.assertEqual(len(list((self.root / "imported_images").iterdir())), 1)

    def test_final_check_handles_catalog_change_during_download(self):
        metadata = {key: ", ".join(value) if isinstance(value, list) else value
                    for key, value in self.candidate.items()}
        metadata["name"] = "Concurrent Import"
        def download(*args, **kwargs):
            import_meme(metadata, self.content, data_dir=self.root)
            return self.content
        self.download.side_effect = download
        result = self.ingest()
        self.assertEqual(result["status"], "duplicate")
        self.assertEqual(result["id"], "concurrent-import")
        self.assertEqual(len(json.loads(self.target.read_text())), 1)

    def test_final_check_runs_under_lock(self):
        from utils.catalog_ingestion import _final_duplicate
        def check(records, upload, root):
            self.assertTrue((root / ".meme-import.lock").exists())
            self.assertFalse((root / "imported_images").exists())
            return _final_duplicate(records, upload, root)
        with patch("utils.catalog_ingestion._final_duplicate", side_effect=check):
            self.assertEqual(self.ingest()["status"], "imported")

    def test_image_write_failure_rolls_back(self):
        with patch("utils.importer.os.fsync", side_effect=OSError("disk full")):
            self.assertEqual(self.ingest()["status"], "error")
        self.assert_no_content()

    def test_metadata_failure_rolls_back(self):
        self.target.write_text("[]")
        with patch("utils.importer.os.replace", side_effect=OSError("disk full")):
            self.assertEqual(self.ingest()["status"], "error")
        self.assertEqual(self.target.read_text(), "[]")
        self.assertEqual(list((self.root / "imported_images").iterdir()), [])
        self.assertFalse(list(self.root.glob(".import-*")))

    def test_invalid_changed_image_and_network_failure(self):
        self.download.return_value = b"corrupt"
        self.assertEqual(self.ingest()["status"], "rejected")
        self.download.return_value = self.content
        self.candidate["content_sha256"] = sha256(b"old image").hexdigest()
        self.assertEqual(self.ingest()["status"], "rejected")
        self.download.side_effect = OSError("offline")
        self.assertEqual(self.ingest()["status"], "error")
        self.assert_no_content()

    def test_malformed_catalog_prevents_download(self):
        self.target.write_text("{")
        self.assertEqual(self.ingest()["status"], "error")
        self.assertEqual(self.target.read_text(), "{")
        self.download.assert_not_called()
