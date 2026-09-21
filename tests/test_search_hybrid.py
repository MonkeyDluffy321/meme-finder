from copy import deepcopy
import unittest
from unittest.mock import patch

from utils.search import search_memes


class HybridRankingTests(unittest.TestCase):
    query = "exhausted worker missing deadline"

    def setUp(self):
        # Distributed evidence passes lexical admission without strong coherence.
        self.first = {"name": "First", "keywords": ["exhausted", "worker", "missing"]}
        self.second = {"name": "Second", "keywords": ["exhausted", "worker", "missing"]}
        self.other = {"name": "Unrelated", "keywords": ["ocean"]}
        self.memes = [self.first, self.second, self.other]
        patcher = patch("utils.semantic.semantic_scores", return_value=[
            (self.second, .90), (self.first, .65), (self.other, .20)])
        self.scores = patcher.start()
        self.addCleanup(patcher.stop)

    def test_descriptive_query_reorders_weak_lexical_candidates(self):
        self.assertEqual(search_memes(self.memes, self.query, use_semantic=False), self.memes[:2])
        self.assertEqual(search_memes(self.memes, self.query), [self.second, self.first])
        self.scores.assert_called_once_with(self.memes, self.query)

    def test_exact_name_and_alias_remain_first_against_semantic_boost(self):
        for field in ("name", "aliases"):
            exact = {"name": "Exact", field: self.query if field == "name" else [self.query]}
            self.scores.return_value = [(self.second, .99), (self.first, .2), (exact, .1)]
            result = search_memes([*self.memes, exact], self.query)
            self.assertIs(result[0], exact)
            self.assertIs(result[1], self.second)

    def test_strong_metadata_tiers_remain_protected(self):
        for field in ("keywords", "situations", "emotions", "categories"):
            exact = {"name": "Exact", field: [self.query]}
            self.scores.return_value = [(self.second, .99), (self.first, .2), (exact, .1)]
            self.assertIs(search_memes([*self.memes, exact], self.query)[0], exact)

    def test_only_strong_results_avoid_model_calls(self):
        exact = {"name": self.query}
        self.assertEqual(search_memes([exact, self.other], self.query), [exact])
        self.scores.assert_not_called()

    def test_confident_semantic_recovery_after_lexical_results(self):
        self.scores.return_value = [(self.other, .85), (self.first, .65), (self.second, .65)]
        self.assertEqual(search_memes(self.memes, self.query), self.memes)
        self.scores.assert_called_once()

    def test_weak_or_ambiguous_semantics_do_not_admit_unrelated_results(self):
        for scores in ([(self.other, .63), (self.first, .3)],
                       [(self.other, .70), (self.first, .69)]):
            self.scores.return_value = scores
            self.assertEqual(search_memes(self.memes, self.query), self.memes[:2])
            self.assertEqual(search_memes(self.memes, "purple dinosaur baking spaceship"), [])

    def test_semantic_failure_or_invalid_scores_preserve_lexical_results(self):
        expected = search_memes(self.memes, self.query, use_semantic=False)
        self.scores.side_effect = RuntimeError("offline")
        self.assertEqual(search_memes(self.memes, self.query), expected)
        self.scores.side_effect = None
        for scores in ([], [(self.first, float("nan"))], [(self.first, float("inf"))],
                       [(self.first, 1.1)], [(deepcopy(self.first), .9)]):
            self.scores.return_value = scores
            self.assertEqual(search_memes(self.memes, self.query), expected)

    def test_short_simple_blank_and_opt_out_avoid_model_calls(self):
        for query in ("worker", "exhausted worker", "exhausted worker missing", " ",
                      "I am a worker with a deadline"):
            self.assertEqual(search_memes(self.memes, query),
                             search_memes(self.memes, query, use_semantic=False))
        search_memes(self.memes, self.query, use_semantic=False)
        self.scores.assert_not_called()

    def test_stable_ties_original_objects_and_no_mutation(self):
        before = deepcopy(self.memes)
        self.scores.return_value = [(self.second, .9), (self.first, .9), (self.other, .1)]
        result = search_memes(self.memes, self.query)
        self.assertIs(result[0], self.first)
        self.assertIs(result[1], self.second)
        self.assertEqual(self.memes, before)

    def test_recovered_fuzzy_name_remains_protected(self):
        target = {"name": "exhausted worker missing deadline"}
        query = "exhaustd worker missng deadlne"
        self.scores.return_value = [(self.other, .99), (target, .1)]
        self.assertIs(search_memes([self.other, target], query)[0], target)
        self.scores.assert_not_called()
