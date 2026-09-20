from copy import deepcopy
from io import StringIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from utils.catalog_indexer import index_catalog, main
from utils.catalog_review import ReviewQueue


class IndexerTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.queue = ReviewQueue(Path(temp.name) / "queue.json")
        self.candidate = dict(name="Test", source_page="https://example.com/one",
                              source_image_url="https://example.com/image.png", content_sha256="abc")
        self.report = dict(candidates=[self.candidate], skipped=[], errors=[], pages_processed=1)
        patcher = patch("utils.catalog_indexer.crawl", return_value=self.report)
        self.crawl = patcher.start()
        self.addCleanup(patcher.stop)

    def test_batch_forwarding_queue_provenance_and_no_ingestion(self):
        before = deepcopy(self.candidate)
        provider = object()
        memes = [{"id": "existing"}]
        with patch("utils.catalog_review.ingest_candidate") as ingest:
            result = index_catalog(["https://example.com/one", "https://example.com/two"], memes,
                                   max_pages=2, max_images=4, queue=self.queue, provider=provider)
        self.crawl.assert_called_once_with(["https://example.com/one", "https://example.com/two"], memes,
                                          max_pages=2, max_images=4, provider=provider)
        self.assertEqual(result["candidates_queued"], 1)
        self.assertEqual(result["pages_processed"], 1)
        self.assertEqual(self.queue.entries("pending")[0]["candidate"], before)
        self.assertEqual(self.candidate, before)
        ingest.assert_not_called()

    def test_repeat_does_not_duplicate_or_reopen_rejection(self):
        args = ["https://example.com/one"]
        index_catalog(args, [], queue=self.queue)
        self.queue.reject(self.queue.entries()[0]["queue_id"])
        result = index_catalog(args, [], queue=self.queue)
        self.assertEqual(result["candidates_queued"], 0)
        self.assertEqual(result["skipped"], 1)
        self.assertEqual(self.queue.entries("pending"), [])

    def test_strict_limits_and_invalid_seeds(self):
        for kwargs in ({"max_pages": 0}, {"max_pages": 11}, {"max_images": 101},
                       {"max_images": True}, {"max_pages": 1.5}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                index_catalog([], [], **kwargs)
        for seeds in (["file:///tmp/a"], "https://example.com"):
            with self.assertRaises(ValueError):
                index_catalog(seeds, [])
        self.crawl.assert_not_called()

    def test_seed_iterator_is_bounded_and_deduplicated(self):
        def seeds():
            yield "https://example.com/a#one"
            yield "https://example.com/a#two"
            raise AssertionError("Read beyond seed budget")
        result = index_catalog(seeds(), [], max_pages=2, queue=self.queue)
        self.assertEqual(self.crawl.call_args.args[0], ["https://example.com/a"])
        self.assertEqual(result["seeds_submitted"], 1)

    def test_crawler_errors_counted_empty_queue_not_written(self):
        self.report.update(candidates=[], errors=[{"reason": "robots"}], skipped=[{}])
        result = index_catalog(["https://example.com"], [], queue=self.queue)
        self.assertEqual(result["errors"], 1)
        self.assertEqual(result["skipped"], 1)
        self.assertFalse(self.queue.path.exists())

    def test_queue_failure_not_reported_as_success(self):
        queue = Mock()
        queue.enqueue.side_effect = OSError("disk full")
        with self.assertRaises(OSError):
            index_catalog(["https://example.com"], [], queue=queue)

    def test_cli_loads_combined_catalog(self):
        summary = {"errors": 0, "candidates_queued": 1}
        with patch("utils.catalog_indexer._read_records", side_effect=[[{"id": "a"}], [{"id": "b"}]]), \
                patch("utils.catalog_indexer.index_catalog", return_value=summary) as index, \
                patch("sys.stdout", new_callable=StringIO):
            self.assertEqual(main(["https://example.com", "--max-pages", "1", "--max-images", "2"]), 0)
        self.assertEqual(index.call_args.args[1], [{"id": "a"}, {"id": "b"}])
