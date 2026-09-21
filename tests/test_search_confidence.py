from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from utils.external_index import search_external_templates
from utils.search import search_memes


ROOT = Path(__file__).resolve().parents[1]


class ConfidenceTests(unittest.TestCase):
    def setUp(self):
        self.memes = json.loads((ROOT / "data/memes.json").read_text(encoding="utf-8"))

    def test_real_split_lexical_match_does_not_qualify(self):
        self.assertEqual(search_memes(self.memes, "men in black", use_semantic=False)[0]["name"], "Roll Safe")
        self.assertEqual(search_memes(self.memes, "men in black", require_strong=True), [])

    def test_semantic_only_match_cannot_stop_fallback_or_trigger_model(self):
        query = "secret agents investigating mysterious extraterrestrial visitors"
        with patch("utils.semantic.semantic_scores", return_value=[(self.memes[0], .70)]) as scores:
            self.assertTrue(search_memes(self.memes, query))
            scores.reset_mock()
            self.assertEqual(search_memes(self.memes, query, require_strong=True), [])
            scores.assert_not_called()

    def test_strong_names_aliases_context_and_typos_remain(self):
        for query in ("Distracted Boyfriend", "Drakeposting", "Dittaced boyfrien",
                      "distrcted", "2 choices", "painful forced smile", "man", "work"):
            with self.subTest(query=query):
                self.assertEqual(search_memes(self.memes, query, require_strong=True),
                                 search_memes(self.memes, query, use_semantic=False))

    def test_weak_external_index_match_abstains_but_exact_alias_survives(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "index.json"
            row = dict(name="Other", aliases=["man", "black"], provider="test", template_id="1",
                       image_url="https://example.com/image.jpg")
            path.write_text(json.dumps({"version": 1, "records": [row]}), encoding="utf-8")
            # Both tokens explicitly supported: use a three-token scattered query
            # to test weak external evidence under the same V1 tier rules.
            row["aliases"].append("agents")
            path.write_text(json.dumps({"version": 1, "records": [row]}), encoding="utf-8")
            self.assertEqual(search_external_templates("black man agents", index_path=path), [])
            row["aliases"] = ["Men in Black"]
            path.write_text(json.dumps({"version": 1, "records": [row]}), encoding="utf-8")
            self.assertEqual(search_external_templates("men in black", index_path=path)[0]["name"], "Other")

    def test_blank_ties_identity_and_no_mutation(self):
        rows = [{"name": "Doge"}, {"name": "Doge"}]
        before = deepcopy(rows)
        for query in ("", "DOGE"):
            results = search_memes(rows, query, require_strong=True)
            self.assertIs(results[0], rows[0])
            self.assertIs(results[1], rows[1])
        self.assertEqual(rows, before)


class ConfidenceAppTests(unittest.TestCase):
    def setUp(self):
        patches = [patch("utils.images.load_preview", return_value=None),
                   patch("utils.images.load_external_preview", return_value=None),
                   patch("utils.semantic.semantic_scores", return_value=[]),
                   patch("utils.external_index.search_external_templates", return_value=[]),
                   patch("utils.web_search.search_web", return_value=[])]
        self.preview, self.external_preview, self.semantic, self.index, self.web = [p.start() for p in patches]
        for p in patches:
            self.addCleanup(p.stop)
        self.app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=20).run()

    def query(self, text):
        self.app.text_input(key="query").set_value(text).run()
        self.assertFalse(self.app.exception)

    def test_weak_local_and_missing_index_allow_explicit_web_fallback(self):
        self.query("men in black")
        self.index.assert_called_once()
        self.assertFalse(any(h.value == "Roll Safe" for h in self.app.subheader))
        self.web.assert_not_called()
        self.app.button(key="search_web").click().run()
        self.web.assert_called_once()

    def test_exact_external_beats_weak_local_semantic_match(self):
        query = "secret agents investigating mysterious extraterrestrial visitors"
        self.semantic.return_value = [({"name": "Roll Safe"}, .70)]
        self.index.return_value = [dict(id="external-test", name=query, external_result=True,
                                       provider="test", image_url="https://example.com/image.jpg", meaning="")]
        self.query(query)
        self.assertTrue(any(h.value == query for h in self.app.subheader))
        self.assertFalse(any(button.key == "search_web" for button in self.app.button))
        self.web.assert_not_called()

    def test_strong_curated_priority(self):
        for query in ("Drakeposting", "Success Kid", "2 choices"):
            self.query(query)
        self.index.assert_not_called()
        self.web.assert_not_called()

    def test_unknown_query_keeps_web_action(self):
        self.query("zxqv jklz")
        self.assertTrue(any(button.key == "search_web" for button in self.app.button))
        self.web.assert_not_called()
