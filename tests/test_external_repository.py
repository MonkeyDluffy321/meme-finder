from copy import deepcopy
import json
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from utils.external_importer import import_templates
from utils.external_index import INDEX_PATH, clean_records, search_external_templates
from utils.external_repository import repository_records


class RepositoryProviderTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.index = self.root / "index.json"
        self.revision = "a" * 40
        self.paths = []

    def template(self, slug, text, image=True):
        directory = self.root / "templates" / slug
        directory.mkdir(parents=True)
        (directory / "config.yml").write_text(text, encoding="utf-8")
        self.paths.append(f"templates/{slug}/config.yml")
        if image:
            self.paths.append(f"templates/{slug}/default.jpg")

    def git(self):
        return patch("utils.external_repository.subprocess.run", side_effect=[
            SimpleNamespace(stdout=self.revision), SimpleNamespace(stdout="\n".join(self.paths))])

    def test_bulk_repository_import_is_searchable_pinned_and_offline(self):
        self.template("its-a-trap", 'name: "It\'s A Trap!"\nsource: https://example.com/trap\naliases: [Admiral Ackbar]')
        self.template("absolute-cinema", 'name: Absolute Cinema')
        protected = [INDEX_PATH.parent / name for name in
                     ("memes.json", "imported_memes.json", "catalog_review.json")]
        before = {p: p.read_bytes() if p.exists() else None for p in protected}
        with self.git() as git:
            report = import_templates(self.root, provider="memegen-repository", index_path=self.index)
        self.assertEqual(report["index_size"], 2)
        result = search_external_templates("ADMIRAL ACKBAR", index_path=self.index)[0]
        self.assertEqual(result["name"], "It's A Trap!")
        self.assertTrue(result["external_result"])
        self.assertIn(self.revision, result["image_url"])
        self.assertTrue(search_external_templates("absolute cinema", index_path=self.index))
        self.assertEqual(git.call_args.kwargs["env"]["GIT_NO_LAZY_FETCH"], "1")
        self.assertEqual(before, {p: p.read_bytes() if p.exists() else None for p in protected})
        with self.git():
            self.assertEqual(import_templates(self.root, provider="memegen-repository",
                                              index_path=self.index)["index_size"], 2)

    def test_malformed_repository_metadata_is_skipped(self):
        for slug, text in (("broken", "name: ["), ("scalar", "42"), ("missing", "aliases: []"),
                           ("unsafe", "!!python/object/apply:os.system ['bad']"),
                           ("bad-alias", "name: Bad\naliases: invalid"),
                           ("private", "name: Private\nsource: http://127.0.0.1/x"),
                           ("large", "#" * 65537), ("good", "name: Good")):
            self.template(slug, text)
        self.template("no-image", "name: No Image", image=False)
        with self.git():
            rows = clean_records(repository_records(self.root))
        self.assertEqual([row["name"] for row in rows], ["Good"])

    def test_repository_failure_does_not_change_index(self):
        self.index.write_text("unchanged", encoding="utf-8")
        with patch("utils.external_repository.subprocess.run", side_effect=subprocess.TimeoutExpired("git", 15)):
            with self.assertRaises(ValueError):
                import_templates(self.root, provider="memegen-repository", index_path=self.index)
        self.assertEqual(self.index.read_text(), "unchanged")

    def test_cross_provider_source_duplicates_preserve_provenance(self):
        first = dict(name="It's A Trap!", provider="original", template_id="ackbar", aliases=["Ackbar"],
                     image_url="https://example.com/one.jpg", source_page="http://example.com/memes/trap/")
        second = dict(first, name="It's a trap", provider="mirror", template_id="its-a-trap",
                      image_url="https://example.com/two.jpg", source_page="https://example.com/memes/trap")
        original = deepcopy([first, second])
        rows = clean_records([first, second, second])
        self.assertEqual(len(rows), 1)
        self.assertEqual({p["provider"] for p in rows[0]["provenance"]}, {"original", "mirror"})
        self.assertEqual(clean_records(rows), rows)
        self.assertEqual([first, second], original)
        self.assertEqual(len(clean_records([first, dict(second, source_page="https://example.com/other")])), 2)

    def test_repeat_cross_provider_import_preserves_primary_and_provenance(self):
        first = dict(name="Doge", provider="first", template_id="doge", aliases=[],
                     image_url="https://example.com/doge.jpg", source_page="https://example.com/doge")
        second = dict(first, provider="second", image_url="https://example.com/mirror.jpg")
        export = self.root / "export.json"
        for row in (first, second, second, first):
            export.write_text(json.dumps([row]), encoding="utf-8")
            self.assertEqual(import_templates(export, provider="json", index_path=self.index)["index_size"], 1)
        result = search_external_templates("DOGE", index_path=self.index)[0]
        self.assertEqual(result["provider"], "first")
        self.assertEqual({p["provider"] for p in result["provenance"]}, {"first", "second"})

    def test_shipped_expansion_keeps_existing_templates(self):
        rows = json.loads(INDEX_PATH.read_text(encoding="utf-8"))["records"]
        self.assertGreater(len(rows), 600)
        for query in ("Business Cat", "DOGE", "Drake", "Success Kid", "it's a trap", "Absolute Cinema"):
            self.assertTrue(search_external_templates(query), query)
        self.assertTrue(any(row["provider"] == "memegen-repository" for row in rows))
