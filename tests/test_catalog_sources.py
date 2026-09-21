from copy import deepcopy
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from utils.catalog_review import ReviewQueue
from utils.catalog_sources import main, run_sources, validate_config


class SourceTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name)
        self.queue = ReviewQueue(self.path / "queue.json")
        self.config = {"sources": [
            {"name": name, "approved": True, "seeds": [f"https://{name}.example/page"]}
            for name in ("one", "two")]}

    def report(self, page, url="https://images.example/a.png", digest="abc"):
        return {"pages_processed": 1, "skipped": [], "errors": [], "candidates": [
            {"source_page": page, "source_image_url": url, "content_sha256": digest}]}

    def test_cross_source_dedup_stats_and_manual_gate(self):
        reports = [self.report(s["seeds"][0], f"https://images.example/{i}.png")
                   for i, s in enumerate(self.config["sources"])]
        with patch("utils.catalog_indexer.crawl", side_effect=reports) as crawl, \
                patch.object(ReviewQueue, "approve") as approve, \
                patch("utils.catalog_review.ingest_candidate") as ingest:
            result = run_sources(self.config, [], queue=self.queue)
        self.assertEqual(result["overall"], dict(pages_processed=2, candidates_discovered=2,
                                              candidates_queued=1, skipped=1, errors=0))
        self.assertEqual(result["sources"][1]["skipped"], 1)
        self.assertEqual(len(self.queue.entries("pending")), 1)
        self.assertEqual(crawl.call_count, 2)
        approve.assert_not_called()
        ingest.assert_not_called()

    def test_same_url_deduplicated_and_rejection_preserved_on_rerun(self):
        first = self.report("https://one.example/page")["candidates"][0]
        identity = self.queue.enqueue([first])[0]
        self.queue.reject(identity)
        with patch("utils.catalog_indexer.crawl", return_value=self.report(
                "https://two.example/page", digest="different")):
            result = run_sources(self.config, [], queue=ReviewQueue(self.queue.path))
        self.assertEqual(result["overall"]["candidates_queued"], 0)
        self.assertEqual(len(self.queue.entries("rejected")), 1)

    def test_source_exception_does_not_stop_next_source(self):
        with patch("utils.catalog_indexer.crawl", side_effect=[RuntimeError("offline"),
                self.report("https://two.example/page")]):
            result = run_sources(self.config, [], queue=self.queue)
        self.assertEqual(result["overall"]["errors"], 1)
        self.assertEqual(result["overall"]["candidates_queued"], 1)

    def test_crawler_errors_and_skips_aggregate(self):
        report = dict(pages_processed=1, candidates=[], errors=[{}], skipped=[{}, {}])
        with patch("utils.catalog_indexer.crawl", return_value=report):
            result = run_sources(self.config, [], queue=self.queue)
        self.assertEqual(result["overall"]["errors"], 2)
        self.assertEqual(result["overall"]["skipped"], 4)

    def test_unapproved_sources_and_normalized_duplicate_seeds(self):
        self.config["sources"][0]["approved"] = False
        self.config["sources"][1]["seeds"] *= 2
        self.config["sources"].append({"name": "three", "approved": True,
                                     "seeds": ["https://two.example/page#fragment"]})
        with patch("utils.catalog_indexer.crawl", return_value=self.report(
                "https://two.example/page")) as crawl:
            result = run_sources(self.config, [], queue=self.queue)
        crawl.assert_called_once()
        self.assertEqual(result["overall"]["skipped"], 3)

    def test_limits_forwarded_without_mutating_config(self):
        self.config["limits"] = {"max_sources": 2, "max_pages": 1, "max_images": 2}
        before = deepcopy(self.config)
        provider, memes = object(), [{"id": "existing"}]
        with patch("utils.catalog_indexer.crawl", return_value=self.report("https://one.example/page")) as crawl:
            run_sources(self.config, memes, queue=self.queue, provider=provider)
        for call in crawl.call_args_list:
            self.assertEqual(call.args[1], memes)
            self.assertEqual(call.kwargs, dict(max_pages=1, max_images=2, provider=provider))
        self.assertEqual(self.config, before)

    def test_invalid_config_fails_before_crawling(self):
        bad = [None, {}, {"sources": [], "typo": 1}]
        for limits in ({"max_sources": 1}, {"max_pages": 0}, {"max_images": 101},
                       {"max_sources": 11}, {"max_pages": True}, {"max_images": 1.5}, {"typo": 1}):
            bad.append({**self.config, "limits": limits})
        for field, value in (("approved", "true"), ("seeds", []), ("seeds", ["file:///a"]),
                             ("seeds", ["https://one.example"] * 4), ("name", "")):
            config = deepcopy(self.config)
            config["sources"][0][field] = value
            bad.append(config)
        duplicate = deepcopy(self.config)
        duplicate["sources"][1]["name"] = "one"
        bad.append(duplicate)
        with patch("utils.catalog_sources.index_catalog") as index:
            for config in bad:
                with self.subTest(config=config), self.assertRaises(ValueError):
                    run_sources(config, [])
        index.assert_not_called()

    def test_cli_catalog_loading_output_and_error_exit(self):
        config_path = self.path / "sources.json"
        config_path.write_text(json.dumps(self.config), encoding="utf-8")
        summary = {"sources": [], "overall": {"errors": 1}}
        with patch("utils.catalog_sources._read_records", side_effect=[[{"id": "a"}], [{"id": "b"}]]), \
                patch("utils.catalog_sources.run_sources", return_value=summary) as run, \
                patch("sys.stdout", new_callable=StringIO) as output:
            self.assertEqual(main(["--config", str(config_path)]), 1)
        self.assertEqual(run.call_args.args[1], [{"id": "a"}, {"id": "b"}])
        self.assertEqual(json.loads(output.getvalue()), summary)

    def test_empty_default_config_is_safe(self):
        with patch("utils.catalog_sources.index_catalog") as index:
            self.assertEqual(run_sources({"sources": []}, [])["overall"]["pages_processed"], 0)
        index.assert_not_called()
