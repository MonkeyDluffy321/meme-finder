import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from utils.meme_index import load_index
from utils.meme_search import search_finished_memes
from utils.search import normalize_query, search_memes
from utils.search_all import search_all


ROOT = Path(__file__).resolve().parents[1]


class SearchAllTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / "instances.json"
        self.rows = [dict(meme_id="caption", provider="fixture", caption_text="Weekend waffles",
                          image_url="https://example.org/waffles.png"),
                     dict(meme_id="choice", provider="fixture", caption_text="2 choices",
                          image_url="https://example.org/choice.png")]
        self.path.write_text(json.dumps({"version": 1, "records": self.rows}), encoding="utf-8")
        self.catalog = json.loads((ROOT / "data/memes.json").read_text(encoding="utf-8"))
        patches = [patch("utils.meme_search.load_index", side_effect=lambda path: load_index(self.path)),
                   patch("utils.external_index.search_external_templates", return_value=[]),
                   patch("utils.semantic.semantic_scores", return_value=[]),
                   patch("utils.images.load_preview", return_value=None),
                   patch("utils.images.load_external_preview", return_value=None)]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def test_independent_group_combinations(self):
        for query, expected in (("Weekend waffles", (True, False)), ("distracted boyfriend", (False, True)),
                                ("2 choices", (True, True)), ("zzqxvv", (False, False))):
            with self.subTest(query=query):
                result = search_all(query, self.catalog)
                self.assertEqual((bool(result["memes"]), bool(result["templates"])), expected)

    def test_engine_order_and_outputs_unchanged(self):
        for query in ("2 choices", "men", "Weekend waffles", ""):
            expected_memes = search_finished_memes(query)
            expected_templates = search_memes(self.catalog, normalize_query(query), require_strong=True)
            result = search_all(query, self.catalog, include_external=False)
            self.assertEqual(result, {"memes": expected_memes, "templates": expected_templates})

    def test_raw_caption_query_and_canonical_template_query(self):
        with patch("utils.meme_search.search_finished_memes", return_value=[]) as finished, \
                patch("utils.search.search_memes", return_value=[]) as templates:
            search_all("choices", self.catalog, include_external=False)
            finished.assert_called_once_with("choices")
            templates.assert_called_once_with(self.catalog, normalize_query("choices"), require_strong=True)

    def test_external_template_fallback_is_independent_of_finished_results(self):
        external = [{"id": "external"}]
        with patch("utils.external_index.search_external_templates", return_value=external) as fallback:
            result = search_all("Weekend waffles", self.catalog)
            self.assertTrue(result["memes"])
            self.assertEqual(result["templates"], external)
            fallback.assert_called_once_with("Weekend waffles")

    def test_ui_group_combinations_and_unidentified_meme(self):
        app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=20).run()
        for query, expected in (("Weekend waffles", (True, False)), ("distracted boyfriend", (False, True)),
                                ("2 choices", (True, True)), ("zzqxvv", (False, False))):
            with self.subTest(query=query):
                app.text_input(key="query").set_value(query).run()
                self.assertFalse(app.exception)
                headings = [h.value for h in app.subheader]
                self.assertEqual(("Finished Memes" in headings, "Templates" in headings), expected)
                if expected[0]:
                    self.assertTrue(any(t.value == query for t in app.text))
                    self.assertFalse(any("No meme matched" in i.value for i in app.info))
                    self.assertFalse(any(b.key == "search_web" for b in app.button))
                if all(expected):
                    self.assertLess(headings.index("Finished Memes"), headings.index("Templates"))

    def test_filters_and_library_do_not_mix_groups(self):
        app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=20).run()
        app.text_input(key="query").set_value("2 choices").run()
        app.multiselect(key="categories").set_value(["money"]).run()
        self.assertFalse(app.exception)
        self.assertIn("Finished Memes", [h.value for h in app.subheader])
        with patch("utils.meme_search.search_finished_memes") as finished:
            app.button(key="saved").click().run()
            finished.assert_not_called()
        self.assertNotIn("Finished Memes", [h.value for h in app.subheader])

    def test_corrupt_finished_preview_keeps_caption(self):
        with patch("utils.images.load_external_preview", return_value=b"invalid"):
            app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=20).run()
            app.text_input(key="query").set_value("Weekend waffles").run()
        self.assertFalse(app.exception)
        self.assertTrue(any(t.value == "Weekend waffles" for t in app.text))
        self.assertTrue(any(c.value == "Preview unavailable" for c in app.caption))
