from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from utils import semantic
from utils.external_importer import enrich_catalog_metadata
from utils.external_index import INDEX_PATH, _load, clean_records, search_external_templates
from utils.external_providers import memegen_records


class ExternalSemanticTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "index.json"
        self.rows = [dict(name=name, provider="test", template_id=str(i), aliases=[],
                          image_url=f"https://example.com/{i}.jpg")
                     for i, name in enumerate(("Distracted Boyfriend", "Two Buttons", "Business Cat", "Surprised Man"))]
        self.write()
        self.addCleanup(_load.cache_clear)

    def write(self):
        self.path.write_text(json.dumps({"version": 1, "records": self.rows}), encoding="utf-8")

    def search(self, query):
        return search_external_templates(query, index_path=self.path)

    def test_descriptive_semantic_recovery_reuses_existing_scorer(self):
        for query, target in (("guy looking at another girl", 0), ("man sweating choosing buttons", 1),
                              ("cat at office desk", 2), ("surprised man looking shocked", 3)):
            def scores(rows, query):
                return [(row, .75 if i == target else .5) for i, row in enumerate(rows)]
            with patch("utils.semantic.semantic_scores", side_effect=scores) as scorer:
                results = self.search(query)
            self.assertEqual(results[0]["name"], self.rows[target]["name"])
            self.assertTrue(results[0]["external_result"])
            scorer.assert_called_once()

    def test_weak_ambiguous_invalid_and_foreign_semantics_abstain(self):
        for best, runner in ((.63, .4), (.70, .69), (.70, .70), (float("nan"), .4), (1.1, .3)):
            with patch("utils.semantic.semantic_scores", side_effect=lambda rows, q: [(rows[0], best), (rows[1], runner)]):
                self.assertEqual(self.search("how to bake chocolate cake"), [])
        with patch("utils.semantic.semantic_scores", return_value=[({"name": "foreign"}, .9)]):
            self.assertEqual(self.search("how to bake chocolate cake"), [])

    def test_names_aliases_short_blank_and_strong_context_skip_model(self):
        self.rows[0]["aliases"] = ["distracted guy meme template"]
        self.rows[1]["description"] = "man sweating choosing buttons"
        self.write()
        with patch("utils.semantic.semantic_scores") as scorer:
            for query in ("Distracted Boyfriend", "DISTRACTED GUY MEME TEMPLATE", "man sweating choosing buttons"):
                self.assertTrue(self.search(query))
            for query in ("", "men in black", "zxqv jklz", "a guy with a person"):
                self.assertEqual(self.search(query), [])
        scorer.assert_not_called()

    def test_model_failure_preserves_lexical_and_fallback(self):
        with patch("utils.semantic.semantic_scores", side_effect=RuntimeError("offline")):
            self.assertEqual(self.search("guy looking at another girl"), [])
            self.assertEqual(self.search("Two Buttons")[0]["name"], "Two Buttons")

    def test_metadata_is_bounded_preserved_and_used_by_existing_search(self):
        self.rows[1].update(description="A sweating man choosing buttons", situations=["difficult decision"],
                            keywords=[None, "sweating man", " ", "SWEATING MAN", "x" * 201])
        self.write()
        results = self.search("man sweating choosing buttons")
        self.assertEqual(results[0]["name"], "Two Buttons")
        text = semantic.build_semantic_text(results[0])
        self.assertIn("difficult decision", text)
        self.assertIn("A sweating man choosing buttons", text)
        self.assertNotIn("https://", text)
        self.assertEqual(results[0]["keywords"], ["sweating man"])
        before = deepcopy(self.rows)
        bad = dict(self.rows[0], description=[], meaning="x" * 2001, situations="invalid")
        cleaned = clean_records([bad])[0]
        self.assertNotIn("description", cleaned)
        self.assertNotIn("meaning", cleaned)
        self.assertNotIn("situations", cleaned)
        self.assertEqual(before, self.rows)

    def test_provider_and_duplicate_metadata_survive(self):
        export = [{"id": "test", "name": "Template", "blank": "https://example.com/image.jpg",
                   "keywords": [None, "office", "cat"], "description": "Cat at an office desk"}]
        adapted = clean_records(memegen_records(export))[0]
        other = dict(adapted, provider="other", keywords=["business"], situations=["work"])
        merged = clean_records([adapted, other])[0]
        self.assertEqual(merged["keywords"], ["office", "cat", "business"])
        self.assertEqual(merged["situations"], ["work"])
        self.assertEqual(merged["description"], "Cat at an office desk")

    def test_catalog_metadata_reuse_requires_unambiguous_exact_identity(self):
        catalog_path = self.path.parent / "memes.json"
        catalog = [dict(name="Example", aliases=["Alternate"], description="Existing trusted description",
                        keywords=["work"], local_image="private.png"),
                   dict(name="Ambiguous", aliases=["shared"]),
                   dict(name="Other", aliases=["shared"])]
        catalog_path.write_text(json.dumps(catalog), encoding="utf-8")
        before = catalog_path.read_bytes()
        rows = [dict(name=name) for name in ("EXAMPLE", "Alternate", "shared", "Example variation")]
        with patch("utils.external_importer.DATA_DIR", self.path.parent):
            enrich_catalog_metadata(rows)
        for row in rows[:2]:
            self.assertEqual(row["description"], "Existing trusted description")
            self.assertEqual(row["keywords"], ["work"])
            self.assertNotIn("local_image", row)
        for row in rows[2:]:
            self.assertNotIn("description", row)
        self.assertEqual(catalog_path.read_bytes(), before)

    def test_shipped_metadata_and_existing_embedding_cache(self):
        rows = json.loads(INDEX_PATH.read_text(encoding="utf-8"))["records"]
        self.assertEqual(len(rows), 712)
        self.assertGreater(sum(bool(row.get("keywords")) for row in rows), 200)
        with patch("utils.semantic.semantic_scores") as scorer:
            self.assertEqual(search_external_templates("guy looking at another girl")[0]["name"], "Distracted Boyfriend")
        scorer.assert_not_called()
        with patch("utils.semantic.semantic_scores", side_effect=lambda rows, q:
                   [(row, .73 if row["name"] == "Two Buttons" else .5) for row in rows]):
            self.assertEqual(search_external_templates("man sweating choosing buttons")[0]["name"], "Two Buttons")
        semantic._document_embeddings.cache_clear()
        semantic._query_embedding.cache_clear()
        self.addCleanup(semantic._document_embeddings.cache_clear)
        self.addCleanup(semantic._query_embedding.cache_clear)
        with patch("utils.semantic.embed_texts", side_effect=lambda texts: [[1., 0.] for _ in texts]) as embed:
            self.search("guy looking at another girl")
            self.search("guy looking at another girl")
            self.assertEqual(embed.call_count, 2)
            self.search("cat at office desk")
            self.assertEqual(embed.call_count, 3)

    def test_search_does_not_write_or_mutate_records(self):
        before = self.path.read_bytes()
        with patch("utils.semantic.semantic_scores", side_effect=lambda rows, q: [(rows[0], .8), (rows[1], .4)]):
            result = self.search("guy looking at another girl")
            result[0]["aliases"].append("changed")
            self.assertNotIn("changed", self.search("guy looking at another girl")[0]["aliases"])
        self.assertEqual(self.path.read_bytes(), before)
