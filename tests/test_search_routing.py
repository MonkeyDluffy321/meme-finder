import json
from pathlib import Path
import unittest
from unittest.mock import patch

from utils.search import normalize_hinglish_query, search_memes
from utils.search_all import search_all, combine_templates


class RoutingTests(unittest.TestCase):
    def setUp(self):
        self.rows = json.loads((Path(__file__).resolve().parents[1] / "data/memes.json").read_text())

    def test_variants_combine_without_semantics(self):
        for noun in ("button", "buttons"):
            for particle in ("me", "mein"):
                with self.subTest(noun=noun, particle=particle), patch(
                        "utils.semantic.semantic_scores", side_effect=AssertionError("No semantics")) as scores:
                    result = search_all(f"do {noun} {particle} choice", self.rows, include_finished=False)
                    names = [r["name"] for r in result["templates"]]
                    self.assertEqual(names[0], "Two Buttons")
                    self.assertEqual(names.count("Two Buttons"), 1)
                    self.assertIn("Both Buttons Pressed", names)
                    scores.assert_not_called()

    def test_english_and_negation_safety(self):
        for query in ("do me a favor", "do not show me buttons", "help me choose", "do work for me"):
            self.assertEqual(normalize_hinglish_query(query, self.rows), query)

    def test_weak_query_still_uses_semantics(self):
        query = "distant lunar observatory researchers"
        with patch("utils.external_index.search_external_templates", return_value=[]) as external, \
                patch("utils.semantic.semantic_scores", return_value=[(self.rows[0], .8)]) as scores:
            result = search_all(query, self.rows, include_finished=False)
            self.assertEqual(result["templates"], [self.rows[0]])
            scores.assert_called_once()
            external.assert_called_once_with(query, lexical_only=True)

    def test_dedup_and_exact_order(self):
        curated = {"name": "Local", "image_url": "https://example.org/a"}
        duplicate = {"name": "Local mirror", "image_url": "https://example.org/a"}
        distinct = {"name": "Exact", "image_url": "https://example.org/b"}
        self.assertEqual(combine_templates([curated], [duplicate, distinct], "Exact"), [distinct, curated])
        same_name = {"name": "Local", "image_url": "https://example.org/c"}
        self.assertEqual(combine_templates([curated], [same_name], "Local"), [curated])
        source = {"name": "Copy", "provider": "fixture", "template_id": "1"}
        mirror = {"name": "Mirror", "provenance": [{"provider": "fixture", "template_id": "1"}]}
        self.assertEqual(combine_templates([source], [mirror], "Copy"), [source])

    def test_cross_catalog_names_aliases_and_related_variants(self):
        curated = {"name": "Quiet Harbor", "aliases": ["Calm Port"]}
        for duplicate in ({"name": "  QUIET-harbor! "}, {"name": "Calm Port"},
                          {"name": "Alternate", "aliases": ["Quiet Harbor"]},
                          {"name": "Alternate", "aliases": ["Calm Port"]}):
            with self.subTest(duplicate=duplicate):
                self.assertEqual(combine_templates([curated], [duplicate], "Quiet Harbor"), [curated])
        related = {"name": "Harbor Storm", "keywords": ["Quiet Harbor", "Calm Port"]}
        self.assertEqual(combine_templates([curated], [related], "Quiet Harbor"), [curated, related])

    def test_ambiguous_aliases_and_nonidentity_similarity_survive(self):
        first = {"name": "First", "aliases": ["Shared"]}
        second = {"name": "Second", "aliases": ["Shared"]}
        ambiguous = {"name": "Third", "aliases": ["Shared"]}
        self.assertEqual(combine_templates([first, second], [ambiguous], "First"),
                         [first, second, ambiguous])
        for first, second in [("Choice", "Decision"), ("Harbor", "Harbors"), ("", "")]:
            local, remote = {"name": first}, {"name": second}
            self.assertEqual(len(combine_templates([local], [remote], "unrelated")), 2)
        self.assertEqual(len(combine_templates([], [{"name": "Same"}, {"name": "Same"}], "Same")), 2)

    def test_external_semantics_after_both_lexical_tiers_abstain(self):
        query = "distant lunar observatory researchers"
        external_result = {"name": "Example", "external_result": True}
        with patch("utils.external_index.search_external_templates", side_effect=[[], [external_result]]) as external, \
                patch("utils.semantic.semantic_fallback", return_value=[]) as semantic:
            result = search_all(query, self.rows, include_finished=False)
            self.assertEqual(result["templates"], [external_result])
            self.assertEqual(external.call_args_list[0].kwargs, {"lexical_only": True})
            self.assertEqual(external.call_args_list[1].kwargs, {"semantic_only": True})
            semantic.assert_called_once()

    def test_individual_strength_removes_weak_tail(self):
        rows = [{"name": "Anchor", "keywords": ["red green blue"]},
                {"name": "Other", "keywords": ["red", "green"]}]
        result = search_memes(rows, "red green blue", use_semantic=False,
                              require_strong=True, strong_only=True)
        self.assertEqual(result, [rows[0]])
