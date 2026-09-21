from io import BytesIO
from pathlib import Path
import unittest
from unittest.mock import patch

from PIL import Image
from streamlit.testing.v1 import AppTest


class WebSearchAppTests(unittest.TestCase):
    def setUp(self):
        buffer = BytesIO()
        Image.new("RGB", (200, 200), "blue").save(buffer, format="PNG")
        self.candidate = dict(id="web-test", name="Temporary meme", meaning="A work reaction",
                              categories=["work"], emotions=["stress"], web_result=True,
                              source_page="https://example.com/page", image_url="https://example.com/image",
                              _web_preview=buffer.getvalue())
        patches = [patch("utils.web_search.search_web", return_value=[self.candidate]),
                   patch("utils.images.load_preview", return_value=None),
                   patch("utils.semantic.semantic_scores", return_value=[]),
                   patch("utils.library_ui.card_actions", return_value=False)]
        self.web, self.preview, self.semantic, self.actions = [p.start() for p in patches]
        for p in patches:
            self.addCleanup(p.stop)
        path = Path(__file__).resolve().parents[1] / "app.py"
        self.app = AppTest.from_file(str(path), default_timeout=15).run()

    def query(self, text):
        self.app.text_input(key="query").set_value(text).run()
        self.assertFalse(self.app.exception)

    def test_local_and_blank_queries_never_offer_or_call_web(self):
        for query in ("", "Drakeposting", "2 choices"):
            self.query(query)
            self.assertFalse(any(button.key == "search_web" for button in self.app.button))
        self.web.assert_not_called()

    def test_explicit_action_cached_reruns_safe_cards_and_source(self):
        self.query("zxqv jklz")
        self.app.run()
        self.web.assert_not_called()
        self.preview.reset_mock()
        self.actions.reset_mock()
        self.app.button(key="search_web").click().run()
        self.assertFalse(self.app.exception)
        self.assertEqual(self.web.call_args.args[1], "zxqv jklz")
        self.assertTrue(any("Temporary web result" in c.value for c in self.app.caption))
        self.assertEqual(len(self.app.get("link_button")), 1)
        self.assertEqual(len(self.app.get("image")), 1)
        self.preview.assert_not_called()
        self.actions.assert_not_called()
        self.app.run()
        self.web.assert_called_once()
        self.assertTrue(self.app.button(key="search_web").disabled)

    def test_query_change_invalidates_cache_and_requires_new_action(self):
        self.query("zxqv")
        self.app.button(key="search_web").click().run()
        self.query("jklz")
        self.assertIsNone(self.app.session_state["live_web_search"]["results"])
        self.assertFalse(any(h.value == "Temporary meme" for h in self.app.subheader))
        self.web.assert_called_once()
        self.app.button(key="search_web").click().run()
        self.assertEqual(self.web.call_count, 2)
        self.assertEqual(self.app.session_state["live_web_search"]["query"], "jklz")
        self.query("drake")
        self.assertIsNone(self.app.session_state["live_web_search"]["results"])
        self.assertTrue(any(h.value == "Drake Hotline Bling" for h in self.app.subheader))
        self.assertEqual(self.web.call_count, 2)

    def test_filters_use_cached_web_results_without_new_crawl(self):
        self.query("zxqv")
        self.app.button(key="search_web").click().run()
        self.app.multiselect(key="categories").set_value(["work"]).run()
        self.assertTrue(any(h.value == "Temporary meme" for h in self.app.subheader))
        self.app.multiselect(key="categories").set_value(["reaction"]).run()
        self.assertFalse(any(h.value == "Temporary meme" for h in self.app.subheader))
        self.web.assert_called_once()

    def test_empty_failure_cached_without_automatic_retry(self):
        self.web.return_value = []
        self.query("zxqv")
        self.app.button(key="search_web").click().run()
        self.app.run()
        self.assertFalse(self.app.exception)
        self.web.assert_called_once()
        self.assertTrue(any("No matching web results" in info.value for info in self.app.info))
