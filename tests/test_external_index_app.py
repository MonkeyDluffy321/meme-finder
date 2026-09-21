from pathlib import Path
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from utils.external_index import search_external_templates


class ExternalIndexAppTests(unittest.TestCase):
    def setUp(self):
        patches = [patch("utils.images.load_preview", return_value=None),
                   patch("utils.images.load_external_preview", return_value=None),
                   patch("utils.semantic.semantic_scores", return_value=[]),
                   patch("utils.web_search.search_web", return_value=[]),
                   patch("utils.external_index.search_external_templates", wraps=search_external_templates)]
        self.local_preview, self.external_preview, self.semantic, self.web, self.index = [p.start() for p in patches]
        for p in patches:
            self.addCleanup(p.stop)
        self.app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=20).run()

    def query(self, text):
        self.app.text_input(key="query").set_value(text).run()
        self.assertFalse(self.app.exception)

    def test_business_cat_uses_index_without_crawl_or_library_actions(self):
        with patch("utils.library_ui.card_actions") as actions:
            self.query("Business Cat")
        self.assertTrue(any(h.value == "Business Cat" for h in self.app.subheader))
        self.assertTrue(any("Not curated" in c.value for c in self.app.caption))
        self.assertTrue(self.external_preview.called)
        actions.assert_not_called()
        self.web.assert_not_called()
        self.assertFalse(any(button.key == "search_web" for button in self.app.button))

    def test_curated_priority_and_blank_browse_skip_index(self):
        for query in ("", "Drakeposting", "Success Kid"):
            self.query(query)
        self.index.assert_not_called()
        self.external_preview.assert_not_called()
        self.web.assert_not_called()

    def test_doge_case_insensitive_external_result(self):
        self.query("DOGE")
        self.assertTrue(any(h.value == "Doge" for h in self.app.subheader))
        self.assertTrue(any("Not curated" in c.value for c in self.app.caption))
        self.web.assert_not_called()

    def test_unknown_query_reaches_existing_explicit_web_fallback(self):
        self.query("zxqv jklz")
        self.index.assert_called_once()
        self.web.assert_not_called()
        self.app.button(key="search_web").click().run()
        self.assertFalse(self.app.exception)
        self.web.assert_called_once()

    def test_index_failure_abstention_keeps_web_fallback(self):
        self.index.return_value = []
        self.index.side_effect = None
        self.query("zxqv")
        self.assertTrue(any(button.key == "search_web" for button in self.app.button))


class ExternalPreviewTests(unittest.TestCase):
    def test_preview_uses_safe_downloader_and_image_validation(self):
        from utils.images import load_external_preview
        load_external_preview.clear()
        self.addCleanup(load_external_preview.clear)
        with patch("utils.images.download_image", return_value=b"not an image") as download:
            self.assertIsNone(load_external_preview("https://example.com/image.jpg"))
        download.assert_called_once_with("https://example.com/image.jpg", respect_indexing=True)
