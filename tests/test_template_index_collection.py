import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from utils.template_index import load_collection, main


class CollectionTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.data_dir = Path(temporary.name)
        self.curated = [{"id": "curated", "name": "Café"}]
        self.write_catalog("memes.json", self.curated)

    def write_catalog(self, filename, entries):
        (self.data_dir / filename).write_text(
            json.dumps(entries, ensure_ascii=False), encoding="utf-8")

    def test_curated_entries_win_and_import_order_is_preserved(self):
        imported = [{"id": "first", "name": "नमस्ते"},
                    {"id": "curated", "name": "Replacement"},
                    {"id": "second", "local_image": "second.jpg"},
                    {"id": "curated", "name": "Another replacement"}]
        self.write_catalog("imported_memes.json", imported)
        self.assertEqual(load_collection(self.data_dir),
                         self.curated + [imported[0], imported[2]])

    def test_missing_imported_catalog(self):
        self.assertEqual(load_collection(self.data_dir), self.curated)

    def test_empty_imported_catalog(self):
        self.write_catalog("imported_memes.json", [])
        self.assertEqual(load_collection(self.data_dir), self.curated)

    def test_non_list_imported_catalog_is_ignored_like_app(self):
        self.write_catalog("imported_memes.json", {"id": "ignored"})
        self.assertEqual(load_collection(self.data_dir), self.curated)

    def test_cli_passes_collection_and_preserves_hash_only(self):
        imported = {"id": "imported"}
        self.write_catalog("imported_memes.json", [imported])
        collection = load_collection(self.data_dir)
        for arguments, embeddings in [([], True), (["--hash-only"], False)]:
            with self.subTest(arguments=arguments), \
                    patch("utils.template_index.load_collection", return_value=collection) as load, \
                    patch("utils.template_index.prepare_index", return_value=(2, embeddings)) as prepare, \
                    patch("builtins.print") as output:
                main(arguments)
                load.assert_called_once_with()
                prepare.assert_called_once_with(collection, use_embeddings=embeddings)
                output.assert_called_once_with(
                    f"Prepared 2/2 references; embeddings: {embeddings}")
