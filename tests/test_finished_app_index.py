import json
from pathlib import Path
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from utils.meme_index import INDEX_PATH, load_index
from utils.meme_search import search_finished_memes
from utils.search_all import search_all


ROOT = Path(__file__).resolve().parents[1]


class PersistentFinishedIndexTests(unittest.TestCase):
    def test_persistent_index_preserves_reviewed_records(self):
        self.assertEqual(INDEX_PATH, ROOT / "data/meme_instances.json")
        raw = json.loads(INDEX_PATH.read_text(encoding="utf-8"))["records"]
        loaded = load_index()
        self.assertEqual(len(raw), 19)
        self.assertEqual(len(loaded), 19)
        self.assertEqual({r["meme_id"]: r["caption_text"] for r in raw},
                         {r["meme_id"]: r["caption_text"] for r in loaded})
        self.assertEqual(sum(r.get("contains_strong_language", False) for r in loaded), 4)

    def test_default_search_and_app_routing_find_reviewed_captions(self):
        rows = {r["meme_id"]: r for r in load_index()}
        profane = "689204c0351ca306581d7287"
        normal = "7ce8b0cf9630e34ecc9bc4b4"
        cases = [("2006 honda", "cfbc9668816e89394a6f991e"),
                 ("change my mind", "54fd3e9e82ab3741b9cbcb85"),
                 (rows[profane]["caption_text"], profane),
                 (rows[normal]["caption_text"], normal)]
        catalog = json.loads((ROOT / "data/memes.json").read_text(encoding="utf-8"))
        with patch("utils.semantic.semantic_scores", return_value=[]), \
                patch("utils.external_index.search_external_templates", return_value=[]):
            for query, expected in cases:
                with self.subTest(query=query):
                    direct = search_finished_memes(query)
                    self.assertEqual(direct[0]["meme_id"], expected)
                    self.assertEqual(search_all(query, catalog)["memes"], direct)
        self.assertTrue(rows[profane]["contains_strong_language"])
        self.assertIn("fucking", rows[profane]["caption_text"])

    def test_home_renders_persistent_finished_result_without_preview(self):
        with patch("utils.images.load_preview", return_value=None), \
                patch("utils.images.load_external_preview", return_value=None), \
                patch("utils.semantic.semantic_scores", return_value=[]):
            app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=20).run()
            app.text_input(key="query").set_value("2006 honda").run()
            self.assertFalse(app.exception)
            self.assertIn("Finished Memes", [h.value for h in app.subheader])
            self.assertTrue(any("2006 Honda Civic" in t.value for t in app.text))
