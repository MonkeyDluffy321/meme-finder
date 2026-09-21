from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import call, patch

from utils.search import search_memes
from utils.web_search import enrich_web_identity, search_web


class WebSearchTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.path = self.root / "sources.json"
        self.config = {"sources": [
            {"name": "blocked", "approved": False, "seeds": ["https://blocked.example/"]},
            {"name": "one", "approved": True, "seeds": ["https://one.example/page#first"]},
            {"name": "two", "approved": True, "seeds": ["https://two.example/page"]}]}
        self.write_config()
        self.candidate = {"name": "Work reaction", "meaning": "Deadline stress", "keywords": ["work"],
                          "source_page": "https://one.example/page", "source_image_url": "https://images.example/a",
                          "content_sha256": "abc", "_web_preview": b"validated preview"}
        self.report = dict(candidates=[self.candidate], skipped=[], errors=[], pages_processed=1)
        crawler = patch("utils.web_search.crawl", return_value=self.report)
        self.crawl = crawler.start()
        self.addCleanup(crawler.stop)
        scorer = patch("utils.semantic.semantic_scores", return_value=[])
        scorer.start()
        self.addCleanup(scorer.stop)

    def write_config(self):
        self.path.write_text(json.dumps(self.config), encoding="utf-8")

    def test_memegen_identity_enrichment_and_short_query_ranking(self):
        for slug, name in (("doge", "Doge"), ("drake", "Drake Hotline Bling"),
                           ("fry", "Futurama Fry"), ("success", "Success Kid")):
            with self.subTest(slug=slug):
                self.candidate.update(name="Untitled meme abc", aliases=[],
                    source_image_url=f"https://api.memegen.link/images/{slug}.jpg?width=300")
                before = deepcopy(self.candidate)
                self.assertEqual(search_memes([self.candidate], slug, use_semantic=False), [])
                results = self.search(slug)
                self.assertEqual(len(results), 1)
                self.assertEqual(results[0]["name"], name)
                self.assertIn(slug, results[0]["aliases"])
                self.assertTrue(results[0]["web_result"])
                for field in ("source_page", "source_image_url", "meaning", "keywords"):
                    self.assertEqual(results[0][field], before[field])
                self.assertEqual(self.candidate, before)

    def test_humanized_slug_and_curated_alternate_alias(self):
        for slug in ("business-cat", "business_cat"):
            candidate = {**self.candidate, "name": "", "aliases": ["Existing"],
                         "source_image_url": f"https://api.memegen.link/images/{slug}.png"}
            enriched = enrich_web_identity(candidate)
            self.assertEqual(enriched["name"], "Business Cat")
            self.assertIn(slug, enriched["aliases"])
            self.assertIn("business cat", enriched["aliases"])
            self.assertIn("Existing", enriched["aliases"])
            self.assertEqual(enrich_web_identity(enriched), enriched)
        fry = enrich_web_identity({"source_image_url": "https://api.memegen.link/images/fry.webp"})
        self.assertIn("Not Sure If", fry["aliases"])
        self.assertEqual(search_memes([fry], "not sure if", use_semantic=False), [fry])

    def test_existing_meaningful_name_and_aliases_preserved(self):
        candidate = {**self.candidate, "aliases": ["Original"],
                     "source_image_url": "https://api.memegen.link/images/doge.jpg"}
        before = deepcopy(candidate)
        enriched = enrich_web_identity(candidate)
        self.assertEqual(enriched["name"], candidate["name"])
        self.assertIn("Original", enriched["aliases"])
        self.assertIn("doge", enriched["aliases"])
        self.assertEqual(candidate, before)
        self.assertIsNot(enriched["aliases"], candidate["aliases"])

    def test_unrecoverable_or_untrusted_urls_preserve_behavior(self):
        for url in (None, "https://oldmeme.example/doge.jpg", "file:///images/doge.jpg",
                    "https://api.memegen.link.evil.example/images/doge.jpg",
                    "https://api.memegen.link@evil.example/images/doge.jpg",
                    "https://user@api.memegen.link/images/doge.jpg",
                    "https://api.memegen.link/images/123.jpg",
                    "https://api.memegen.link/images/doge/caption.jpg",
                    "https://api.memegen.link/images/%64oge.jpg",
                    "https://api.memegen.link/images/doge.svg",
                    "https://api.memegen.link/gallery?image=/images/doge.jpg"):
            with self.subTest(url=url):
                candidate = {**self.candidate, "source_image_url": url}
                self.assertEqual(enrich_web_identity(candidate), candidate)

    def search(self, query="work", memes=None):
        return search_web(memes or [], query, config_path=self.path)

    def test_approved_only_and_global_interactive_limits(self):
        self.search()
        self.assertEqual(self.crawl.call_args_list, [
            call([f"https://{source}.example/page"], [], provider=None,
                 max_pages=1, images_per_page=2, max_images=2, delay=.5,
                 include_preview=True, max_robot_delay=2) for source in ("one", "two")])

    def test_seed_dedup_and_source_limit(self):
        self.config["sources"][2]["seeds"] = ["https://one.example/page#again", "https://two.example/page"]
        self.config["sources"].append({"name": "three", "approved": True, "seeds": ["https://three.example/"]})
        self.write_config()
        self.search()
        self.assertEqual([c.args[0] for c in self.crawl.call_args_list],
                         [["https://one.example/page"], ["https://two.example/page"]])

    def test_each_source_contributes_without_first_consuming_budget(self):
        def discover(seeds, memes, **limits):
            return {"candidates": [{**self.candidate, "source_page": seeds[0],
                    "source_image_url": seeds[0] + f"/image-{i}",
                    "content_sha256": seeds[0] + str(i)} for i in range(limits["max_images"])]}
        self.crawl.side_effect = discover
        with patch("utils.web_search.search_memes", wraps=search_memes) as rank:
            results = self.search()
        self.assertEqual([r["source_page"] for r in results],
                         ["https://one.example/page"] * 2 + ["https://two.example/page"] * 2)
        self.assertTrue(all(r["web_result"] for r in results))
        rank.assert_called_once()
        self.assertEqual(len(rank.call_args.args[0]), 4)

    def test_global_caps_and_lower_limits_for_all_budget_combinations(self):
        for pages in (1, 2, 3):
            for images in (1, 2, 3, 4, 5):
                with self.subTest(pages=pages, images=images):
                    self.config["limits"] = {"max_pages": pages, "max_images": images}
                    self.write_config()
                    self.crawl.reset_mock()
                    self.search()
                    calls = self.crawl.call_args_list
                    self.assertEqual(len(calls), min(2, pages, images))
                    self.assertLessEqual(sum(c.kwargs["max_pages"] for c in calls), min(2, pages))
                    self.assertLessEqual(sum(c.kwargs["max_images"] for c in calls), min(4, images))
                    self.assertTrue(all(len(c.args[0]) <= c.kwargs["max_pages"] for c in calls))
                    if len(calls) == 2:
                        self.assertLessEqual(abs(calls[0].kwargs["max_images"] - calls[1].kwargs["max_images"]), 1)

    def test_single_source_can_use_global_budget(self):
        self.config["sources"] = self.config["sources"][1:2]
        self.config["sources"][0]["seeds"].append("https://one.example/second")
        self.write_config()
        self.search()
        self.assertEqual(self.crawl.call_count, 1)
        self.assertEqual(self.crawl.call_args.args[0], ["https://one.example/page", "https://one.example/second"])
        self.assertEqual(self.crawl.call_args.kwargs["max_pages"], 2)
        self.assertEqual(self.crawl.call_args.kwargs["max_images"], 4)

    def test_source_failure_does_not_block_other_source(self):
        second = {**self.candidate, "source_page": "https://two.example/page"}
        self.crawl.side_effect = [OSError("offline"), {"candidates": [second]}]
        results = self.search()
        self.assertEqual(self.crawl.call_count, 2)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["source_page"], second["source_page"])
        self.assertEqual(self.crawl.call_args.kwargs["max_images"], 2)

    def test_cross_source_url_and_hash_duplicates_keep_first_provenance(self):
        for duplicate in ({**self.candidate, "content_sha256": "different"},
                          {**self.candidate, "source_image_url": "https://images.example/mirror"}):
            self.crawl.side_effect = [self.report, {"candidates": [
                {**duplicate, "source_page": "https://two.example/page"}]}]
            results = self.search()
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]["source_page"], self.candidate["source_page"])

    def test_stricter_config_limits_respected(self):
        self.config["limits"] = {"max_pages": 1, "max_images": 1}
        self.write_config()
        self.search()
        self.assertEqual(self.crawl.call_args.args[0], ["https://one.example/page"])
        self.assertEqual(self.crawl.call_args.kwargs["max_pages"], 1)
        self.assertEqual(self.crawl.call_args.kwargs["max_images"], 1)

    def test_ranked_by_v1_renderable_and_no_mutation(self):
        before = deepcopy(self.candidate)
        irrelevant = {**self.candidate, "name": "Ocean", "keywords": [],
                      "source_image_url": "https://images.example/b", "content_sha256": "def"}
        self.report["candidates"] = [irrelevant, self.candidate]
        with patch("utils.web_search.search_memes", wraps=search_memes) as rank:
            results = self.search()
        rank.assert_called_once()
        self.assertEqual(rank.call_args.args[1], "work")
        self.assertEqual(len(results), 1)
        result = results[0]
        self.assertTrue(result["web_result"])
        self.assertTrue(result["id"].startswith("web-"))
        self.assertEqual(result["image_url"], before["source_image_url"])
        self.assertEqual(result["source_page"], before["source_page"])
        self.assertEqual(result["_web_preview"], before["_web_preview"])
        self.assertEqual(self.candidate, before)
        self.assertIsNot(result, self.candidate)

    def test_deduplicate_urls_hashes_and_catalog_records(self):
        self.report["candidates"] = [self.candidate,
            {**self.candidate, "source_image_url": "https://images.example/a#fragment", "content_sha256": "def"},
            {**self.candidate, "source_image_url": "https://images.example/b"}]
        self.assertEqual(len(self.search()), 1)
        catalog = [{"id": "permanent", "image_url": self.candidate["source_image_url"]}]
        before = deepcopy(catalog)
        self.assertFalse(any(row["image_url"] == catalog[0]["image_url"] for row in self.search(memes=catalog)))
        self.assertEqual(catalog, before)

    def test_no_queue_ingestion_or_catalog_writes(self):
        review = self.root / "catalog_review.json"
        permanent = self.root / "memes.json"
        permanent.write_text("[]", encoding="utf-8")
        with patch("utils.catalog_review.QUEUE_PATH", review), \
                patch("utils.catalog_review.ReviewQueue.enqueue") as enqueue, \
                patch("utils.catalog_review.ReviewQueue.approve") as approve, \
                patch("utils.catalog_ingestion.ingest_candidate") as ingest, \
                patch("utils.importer._write_records") as write, \
                patch.object(Path, "write_text", side_effect=AssertionError("write")), \
                patch.object(Path, "write_bytes", side_effect=AssertionError("write")):
            self.assertTrue(self.search())
        for mock in (enqueue, approve, ingest, write):
            mock.assert_not_called()
        self.assertFalse(review.exists())
        self.assertEqual(permanent.read_text(), "[]")
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), ["memes.json", "sources.json"])

    def test_failures_abstain_and_partial_crawl_results_survive(self):
        self.crawl.side_effect = OSError("offline")
        self.assertEqual(self.search(), [])
        self.assertEqual(search_memes([{"name": "work"}], "work"), [{"name": "work"}])
        self.crawl.side_effect = None
        self.report["errors"] = [{"reason": "second source failed"}]
        self.assertEqual(len(self.search()), 1)
        self.report["candidates"] = []
        self.assertEqual(self.search(), [])

    def test_invalid_missing_empty_or_unapproved_config_never_crawls(self):
        self.path.unlink()
        self.assertEqual(self.search(), [])
        self.path.write_text("{", encoding="utf-8")
        self.assertEqual(self.search(), [])
        for config in ({"sources": []}, {"sources": self.config["sources"][:1]},
                       {"sources": [], "limits": {"max_images": 999}}):
            self.config = config
            self.write_config()
            self.assertEqual(self.search(), [])
        self.crawl.assert_not_called()

    def test_query_urls_never_become_seeds_and_blank_never_crawls(self):
        self.assertEqual(self.search(" "), [])
        self.crawl.assert_not_called()
        self.search("https://127.0.0.1/private")
        self.assertNotIn("127.0.0.1", str(self.crawl.call_args.args[0]))

    def test_invalid_candidate_urls_and_outside_seed_pages_skipped(self):
        self.report["candidates"] = [{**self.candidate, "source_image_url": "file:///secret"},
                                     {**self.candidate, "source_page": "https://blocked.example/"}]
        self.assertEqual(self.search(), [])
