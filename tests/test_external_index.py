from copy import deepcopy
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from utils.external_importer import import_templates, main
from utils.external_index import (INDEX_PATH, MAX_RECORDS, _load, clean_records,
                                  search_external_templates)


def record(name="Business Cat", identity="business", **extra):
    return dict(name=name, aliases=[identity], provider="memegen", template_id=identity,
                image_url=f"https://api.memegen.link/images/{identity}.jpg",
                source_page="https://example.com/templates/" + identity, **extra)


class ExternalIndexTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / "index.json"
        self.input = Path(temp.name) / "export.json"
        self.rows = [record(), record("Doge", "doge"), record("Drake Hotline Bling", "drake"),
                     record("Success Kid", "success")]
        self.write(self.rows)
        self.addCleanup(_load.cache_clear)

    def write(self, rows):
        self.path.write_text(json.dumps({"version": 1, "records": rows}), encoding="utf-8")

    def search(self, query):
        return search_external_templates(query, index_path=self.path)

    def test_names_case_aliases_and_external_identity(self):
        for query, expected in (("Business Cat", "Business Cat"), ("DOGE", "Doge"),
                                ("drake", "Drake Hotline Bling"), ("success", "Success Kid")):
            result = self.search(query)[0]
            self.assertEqual(result["name"], expected)
            self.assertTrue(result["external_result"])
            self.assertTrue(result["id"].startswith("external-"))
        self.assertEqual(self.search("business")[0]["name"], "Business Cat")

    def test_shipped_index_contains_required_templates(self):
        for query in ("Business Cat", "DOGE", "Drake", "Success Kid"):
            self.assertTrue(search_external_templates(query), query)
        self.assertGreater(len(json.loads(INDEX_PATH.read_text(encoding="utf-8"))["records"]), 100)

    def test_reuses_v1_without_semantics_and_never_downloads_during_search(self):
        from utils.search import search_memes
        with patch("utils.external_index.search_memes", wraps=search_memes) as rank, \
                patch("utils.semantic.semantic_scores") as semantic, \
                patch("utils.importer_url.download_resource") as download:
            self.assertTrue(self.search("Business Cat"))
        self.assertEqual(rank.call_args.kwargs, {"use_semantic": False, "require_strong": True})
        semantic.assert_not_called()
        download.assert_not_called()

    def test_malformed_rows_skipped_and_untrusted_flags_stripped(self):
        bad = [None, [], {}, {**self.rows[0], "name": 2}, {**self.rows[0], "aliases": "cat"},
               {**self.rows[0], "aliases": [None]}, {**self.rows[0], "image_url": "file:///private"},
               {**self.rows[0], "image_url": "http://127.0.0.1/image"},
               {**self.rows[0], "image_url": "http://[64:ff9b::7f00:1]/image"},
               {**self.rows[0], "source_page": "javascript:alert(1)"}]
        self.write([*bad, {**self.rows[1], "local_image": "secret.png", "external_result": False}])
        results = self.search("DOGE")
        self.assertEqual(len(results), 1)
        self.assertNotIn("local_image", results[0])
        self.assertTrue(results[0]["external_result"])

    def test_missing_broken_wrong_version_and_oversized_indexes_abstain(self):
        for data in ("{", "[]", '{"version":2,"records":[]}',
                     json.dumps({"version": 1, "records": [None] * (MAX_RECORDS + 1)})):
            self.path.write_text(data, encoding="utf-8")
            self.assertEqual(self.search("doge"), [])
        self.path.unlink()
        self.assertEqual(self.search("doge"), [])

    def test_duplicates_merge_aliases_and_namespace_provider_ids(self):
        duplicate = {**self.rows[0], "name": "Office Cat", "aliases": ["Boss Cat"]}
        mirrored = {**self.rows[0], "provider": "other", "template_id": "cat"}
        distinct = {**self.rows[0], "provider": "other", "image_url": "https://example.com/other.jpg"}
        rows = clean_records([self.rows[0], duplicate, mirrored, distinct])
        self.assertEqual(len(rows), 2)
        self.assertIn("Boss Cat", rows[0]["aliases"])
        self.write([self.rows[0], duplicate, mirrored])
        self.assertEqual(len(self.search("cat")), 1)
        self.assertEqual(self.search("office cat")[0]["name"], "Business Cat")

    def test_cache_invalidation_copy_isolation_and_no_catalog_writes(self):
        catalog_paths = [INDEX_PATH.parent / name for name in
                         ("memes.json", "imported_memes.json", "catalog_review.json")]
        before = {path: path.read_bytes() if path.exists() else None for path in catalog_paths}
        with patch("utils.importer._write_records") as write:
            result = self.search("business cat")
            result[0]["aliases"].append("mutated")
            self.assertNotIn("mutated", self.search("business cat")[0]["aliases"])
            self.write([record("Changed Business Cat", "business")])
            self.assertEqual(self.search("business")[0]["name"], "Changed Business Cat")
            self.assertEqual(self.search("zxqv jklz"), [])
            self.assertEqual(self.search(" "), [])
        write.assert_not_called()
        self.assertEqual(before, {path: path.read_bytes() if path.exists() else None for path in catalog_paths})

    def test_memegen_import_and_repeat_upsert(self):
        export = [{"id": "business", "name": "Business Cat", "blank": self.rows[0]["image_url"],
                   "source": self.rows[0]["source_page"]}, None]
        self.input.write_text(json.dumps(export), encoding="utf-8")
        report = import_templates(self.input, provider="memegen", index_path=self.path)
        self.assertEqual(report["accepted_records"], 1)
        self.assertEqual(report["index_size"], 4)
        self.assertEqual(import_templates(self.input, provider="memegen", index_path=self.path)["index_size"], 4)
        self.assertEqual(self.search("business")[0]["name"], "Business Cat")

    def test_generic_json_provider_and_cli(self):
        self.input.write_text(json.dumps([record("New Template", "new")]), encoding="utf-8")
        with patch("sys.stdout", new_callable=StringIO) as output:
            self.assertEqual(main(["--provider", "json", "--input", str(self.input),
                                   "--index", str(self.path)]), 0)
        self.assertEqual(json.loads(output.getvalue())["index_size"], 5)

    def test_failed_import_does_not_destroy_index_or_target_catalog(self):
        before = self.path.read_bytes()
        for export in ([], [None], {}, [{"id": "x", "aliases": "invalid"}]):
            self.input.write_text(json.dumps(export), encoding="utf-8")
            with self.assertRaises(ValueError):
                import_templates(self.input, provider="memegen", index_path=self.path)
            self.assertEqual(self.path.read_bytes(), before)
        for name in ("memes.json", "imported_memes.json", "catalog_review.json"):
            with self.assertRaisesRegex(ValueError, "catalog/review"):
                import_templates(self.input, provider="json", index_path=INDEX_PATH.parent / name)

    def test_atomic_write_failure_preserves_previous_index(self):
        self.input.write_text(json.dumps(self.rows), encoding="utf-8")
        before = self.path.read_bytes()
        with patch("utils.importer.os.replace", side_effect=OSError("disk")):
            with self.assertRaises(OSError):
                import_templates(self.input, provider="json", index_path=self.path)
        self.assertEqual(self.path.read_bytes(), before)
