import copy
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from utils import semantic
from utils.search import search_memes


class HybridTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.memes = json.loads((Path(__file__).resolve().parents[1] / "data/memes.json").read_text())

    def setUp(self):
        self.provider = patch("utils.semantic.semantic_scores").start()
        self.addCleanup(patch.stopall)
        self.target = self.memes[3]
        self.provider.return_value = [(self.target, 0.70), (self.memes[0], 0.60)]

    def test_lexical_precedence(self):
        for query, expected in [("distracted boyfriend", "Distracted Boyfriend"),
                                ("Drakeposting", "Drake Hotline Bling"),
                                ("painful forced smile", "Hide the Pain Harold"),
                                ("Dittaced boyfrien", "Distracted Boyfriend"),
                                ("2 choices", "Two Buttons")]:
            with self.subTest(query=query):
                self.assertEqual(search_memes(self.memes, query)[0]["name"], expected)
        self.provider.assert_not_called()

    def test_paraphrase_recovery(self):
        result = search_memes(self.memes, "I have to choose between two terrible options")
        self.assertEqual(result, [self.target])
        self.assertIs(result[0], self.target)
        self.provider.assert_called_once()

    def test_low_score_rejected(self):
        self.provider.return_value = [(self.target, 0.63)]
        self.assertEqual(search_memes(self.memes, "how to bake chocolate cake"), [])

    def test_ambiguous_score_rejected(self):
        self.provider.return_value = [(self.target, 0.70), (self.memes[0], 0.69)]
        self.assertEqual(search_memes(self.memes, "how to bake chocolate cake"), [])

    def test_short_and_generic_queries_never_expand(self):
        for query in ["zxqv jklz", "quantum spaceship", "boyfriend zxqv jklz"]:
            self.assertEqual(search_memes(self.memes, query), [])
        for query in ["man", "woman", "guy"]:
            self.assertTrue(search_memes(self.memes, query))
        self.provider.assert_not_called()

    def test_negative_calibration_scores_rejected(self):
        for query, score in [("weather forecast in paris", 0.4931),
                             ("how to bake chocolate cake", 0.4899),
                             ("purple dinosaur taxes", 0.5525)]:
            self.provider.return_value = [(self.target, score)]
            self.assertEqual(search_memes(self.memes, query), [])

    def test_provider_failure(self):
        self.provider.side_effect = RuntimeError("unavailable")
        self.assertEqual(search_memes(self.memes, "how to bake chocolate cake"), [])
        self.assertEqual(search_memes(self.memes, "2 choices")[0]["name"], "Two Buttons")

    def test_blank_query(self):
        result = search_memes(self.memes, "  ")
        self.assertEqual(result, self.memes)
        self.assertIsNot(result, self.memes)
        self.provider.assert_not_called()

    def test_nonfinite_scores_rejected(self):
        for score in [float("nan"), float("inf")]:
            self.provider.return_value = [(self.target, score)]
            self.assertEqual(search_memes(self.memes, "how to bake chocolate cake"), [])


class SemanticProviderTests(unittest.TestCase):
    def setUp(self):
        semantic._load_embedding_model.cache_clear()
        semantic._document_embeddings.cache_clear()
        semantic._query_embedding.cache_clear()
        self.addCleanup(self.clear_caches)

    def clear_caches(self):
        semantic._load_embedding_model.cache_clear()
        semantic._document_embeddings.cache_clear()
        semantic._query_embedding.cache_clear()

    def test_model_loaded_once(self):
        factory = Mock(return_value=object())
        with patch.dict(sys.modules, {"fastembed": SimpleNamespace(TextEmbedding=factory)}):
            self.assertIs(semantic.get_embedding_model(), semantic.get_embedding_model())
        factory.assert_called_once_with(model_name=semantic.MODEL_NAME)

    def test_model_initialization_failure_cached(self):
        factory = Mock(side_effect=RuntimeError("missing assets"))
        with patch.dict(sys.modules, {"fastembed": SimpleNamespace(TextEmbedding=factory)}):
            for _ in range(2):
                self.assertEqual(semantic.semantic_fallback([{"name": "Example"}], "how to bake chocolate cake"), [])
        factory.assert_called_once()

    def test_missing_dependency(self):
        with patch.dict(sys.modules, {"fastembed": None}):
            self.assertIsNone(semantic.get_embedding_model())
            self.assertIsNone(semantic.get_embedding_model())

    def test_content_and_query_caches(self):
        memes = [{"name": "One", "meaning": "first"}, {"name": "Two"}]
        before = copy.deepcopy(memes)
        with patch("utils.semantic.embed_texts", side_effect=lambda texts: [[1., 0.] for _ in texts]) as embed:
            semantic.semantic_scores(memes, "first query")
            semantic.semantic_scores(copy.deepcopy(memes), "first query")
            self.assertEqual(embed.call_count, 2)
            semantic.semantic_scores(memes, "second query")
            self.assertEqual(embed.call_count, 3)
            memes[0]["image_url"] = "changed"
            semantic.semantic_scores(memes, "second query")
            self.assertEqual(embed.call_count, 3)
            memes[0]["meaning"] = "changed"
            semantic.semantic_scores(memes, "second query")
            self.assertEqual(embed.call_count, 4)
        self.assertEqual(before[1], memes[1])

    def test_stable_ties_and_original_identity(self):
        memes = [{"name": "One"}, {"name": "Two"}]
        with patch("utils.semantic.embed_texts", side_effect=lambda texts: [[1., 0.] for _ in texts]):
            scores = semantic.semantic_scores(memes, "query")
        self.assertIs(scores[0][0], memes[0])
        self.assertIs(scores[1][0], memes[1])

    def test_embedding_failure(self):
        with patch("utils.semantic.embed_texts", side_effect=RuntimeError("failed")):
            self.assertEqual(semantic.semantic_fallback([{"name": "Example"}], "how to bake chocolate cake"), [])

    def test_cosine(self):
        self.assertAlmostEqual(semantic.cosine_similarity([1, 0], [1, 0]), 1)
        self.assertEqual(semantic.cosine_similarity([0, 0], [1, 0]), 0)


if __name__ == "__main__":
    unittest.main()
