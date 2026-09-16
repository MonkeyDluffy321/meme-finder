import copy
import unittest
from unittest.mock import patch

from utils.explanations import explain, related_memes


class ExplanationTests(unittest.TestCase):
    def setUp(self):
        self.memes = [{"id": "a", "name": "A", "description": "Scene", "meaning": "Meaning",
                       "situations": ["Use"], "categories": ["choice"]},
                      {"id": "b", "name": "B", "categories": ["choice"]},
                      {"id": "c", "name": "C", "categories": ["unrelated"]}]

    def test_metadata_fidelity_and_no_mutation(self):
        original = copy.deepcopy(self.memes[0])
        result = explain(self.memes[0])
        self.assertEqual(result, {k: original[k] for k in ("name", "description", "meaning", "situations")})
        self.assertEqual(self.memes[0], original)

    def test_recommendations_deduplicate_and_exclude_match(self):
        with patch("utils.explanations.search_memes", return_value=self.memes * 2):
            self.assertEqual([m["id"] for m in related_memes(self.memes, self.memes[0], "caption")], ["b", "c"])

    def test_empty_text_does_not_browse_all(self):
        with patch("utils.explanations.search_memes") as search:
            self.assertEqual(related_memes(self.memes, text="  "), [])
            search.assert_not_called()

    def test_search_failure_preserves_metadata_suggestions(self):
        with patch("utils.explanations.search_memes", side_effect=RuntimeError()):
            self.assertEqual(related_memes(self.memes, self.memes[0], "caption"), [self.memes[1]])

    def test_caption_search_never_uses_global_semantic_query_cache(self):
        with patch("utils.search.semantic_fallback") as semantic:
            related_memes(self.memes, text="this private caption has no match")
            semantic.assert_not_called()
