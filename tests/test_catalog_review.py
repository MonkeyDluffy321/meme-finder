from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from utils.catalog_review import ReviewError, ReviewQueue


class ReviewTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / "queue.json"
        self.queue = ReviewQueue(self.path)
        self.candidate = {"source_page": "https://example.com/page", "source_image_url": "https://example.com/image",
                          "name": "Original", "meaning": "A meaning", "keywords": ["work"]}
        self.identity = self.queue.enqueue([self.candidate])[0]

    def test_pending_storage_retrieval_reload_and_copy(self):
        self.candidate["name"] = "Changed outside"
        rows = ReviewQueue(self.path).entries("pending")
        self.assertEqual(rows[0]["candidate"]["name"], "Original")
        rows[0]["candidate"]["name"] = "Changed result"
        self.assertEqual(self.queue.entries()[0]["candidate"]["name"], "Original")

    @patch("utils.catalog_review.ingest_candidate", return_value={"status": "imported", "id": "edited", "message": "Done"})
    def test_approve_edits_persistence_and_no_input_mutation(self, ingest):
        before = deepcopy(self.candidate)
        edits = {"name": "Edited", "aliases": ["Alias"]}
        result = self.queue.approve(self.identity, edits)
        self.assertEqual(result["status"], "imported")
        self.assertEqual(ingest.call_args.args[0]["name"], "Edited")
        self.assertEqual(ingest.call_args.kwargs, {"approved": True, "data_dir": None})
        self.assertEqual(self.candidate, before)
        self.assertEqual(ReviewQueue(self.path).entries("pending"), [])
        self.assertEqual(self.queue.entries()[0]["status"], "imported")

    @patch("utils.catalog_review.ingest_candidate")
    def test_reject_never_ingests_and_survives_reload_reenqueue(self, ingest):
        self.queue.reject(self.identity)
        self.assertEqual(self.queue.enqueue([self.candidate]), [])
        self.assertEqual(ReviewQueue(self.path).entries()[0]["status"], "rejected")
        self.assertEqual(self.queue.entries("pending"), [])
        ingest.assert_not_called()

    @patch("utils.catalog_review.ingest_candidate", return_value={"status": "duplicate", "id": "existing", "message": "Duplicate"})
    def test_duplicate_is_terminal(self, ingest):
        self.assertEqual(self.queue.approve(self.identity)["status"], "duplicate")
        self.assertEqual(self.queue.entries("pending"), [])
        with self.assertRaises(ReviewError):
            self.queue.retry(self.identity)

    @patch("utils.catalog_review.ingest_candidate", return_value={"status": "error", "id": None, "message": "Offline"})
    def test_error_preserves_edits_for_explicit_retry(self, ingest):
        self.queue.approve(self.identity, {"meaning": "Edited meaning"})
        self.assertEqual(self.queue.entries("pending"), [])
        row = ReviewQueue(self.path).entries("error")[0]
        self.assertEqual(row["candidate"]["meaning"], "Edited meaning")
        self.assertEqual(row["result"]["message"], "Offline")
        self.queue.retry(self.identity)
        self.assertEqual(len(self.queue.entries("pending")), 1)

    @patch("utils.catalog_review.ingest_candidate", return_value={"status": "imported", "id": "a", "message": "Done"})
    def test_double_approval_prevented(self, ingest):
        self.queue.approve(self.identity)
        with self.assertRaises(ReviewError):
            self.queue.approve(self.identity)
        ingest.assert_called_once()

    def test_concurrent_approval_prevented(self):
        def ingest(*args, **kwargs):
            with self.assertRaisesRegex(ReviewError, "busy"):
                ReviewQueue(self.path).approve(self.identity)
            return {"status": "imported", "id": "a", "message": "Done"}
        with patch("utils.catalog_review.ingest_candidate", side_effect=ingest):
            self.queue.approve(self.identity)

    @patch("utils.catalog_review.ingest_candidate", side_effect=RuntimeError())
    def test_unexpected_failure_persisted(self, ingest):
        self.assertEqual(self.queue.approve(self.identity)["status"], "error")
        self.assertEqual(self.queue.entries()[0]["status"], "error")

    @patch("utils.catalog_review.ingest_candidate")
    def test_atomic_failure_before_ingestion(self, ingest):
        before = self.path.read_bytes()
        with patch("utils.importer.os.replace", side_effect=OSError("disk")):
            with self.assertRaises(OSError):
                self.queue.approve(self.identity)
        self.assertEqual(self.path.read_bytes(), before)
        ingest.assert_not_called()

    def test_final_write_failure_leaves_recoverable_error(self):
        def ingest(*args, **kwargs):
            self.assertEqual(self.queue.entries()[0]["status"], "error")
            return {"status": "imported", "id": "a", "message": "Done"}
        from utils.importer import _write_records
        count = 0
        def write(*args):
            nonlocal count
            count += 1
            if count == 2:
                raise OSError("disk")
            _write_records(*args)
        with patch("utils.catalog_review.ingest_candidate", side_effect=ingest), \
                patch("utils.catalog_review._write_records", side_effect=write):
            with self.assertRaises(OSError):
                self.queue.approve(self.identity)
        self.assertEqual(ReviewQueue(self.path).entries()[0]["status"], "error")

    def test_malformed_queue_not_overwritten(self):
        self.path.write_text("{")
        with self.assertRaises(ReviewError):
            self.queue.enqueue([self.candidate])
        self.assertEqual(self.path.read_text(), "{")

    def test_provenance_cannot_be_edited(self):
        with self.assertRaises(ReviewError):
            self.queue.approve(self.identity, {"source_image_url": "https://different.com"})

    def test_admin_app_disabled_without_token(self):
        app_path = Path(__file__).resolve().parents[1] / "admin_review.py"
        with patch.dict("os.environ", {"MEME_FINDER_REVIEW_TOKEN": ""}), \
                patch("utils.catalog_review.ReviewQueue.entries") as entries:
            app = AppTest.from_file(str(app_path)).run()
        self.assertFalse(app.exception)
        self.assertTrue(any("disabled" in item.value for item in app.error))
        entries.assert_not_called()

    def test_admin_ui_reject_and_gate(self):
        app_path = Path(__file__).resolve().parents[1] / "admin_review.py"
        with patch.dict("os.environ", {"MEME_FINDER_REVIEW_TOKEN": "x" * 32}), \
                patch("utils.catalog_review.ReviewQueue", return_value=self.queue), \
                patch("utils.catalog_review.ingest_candidate") as ingest:
            app = AppTest.from_file(str(app_path)).run()
            self.assertEqual(len(app.selectbox), 0)
            app.text_input(key="review_admin_token").set_value("x" * 32).run()
            self.assertFalse(app.exception)
            next(button for button in app.button if button.label == "Reject").click().run()
            self.assertFalse(app.exception)
            self.assertEqual(self.queue.entries()[0]["status"], "rejected")
            ingest.assert_not_called()
