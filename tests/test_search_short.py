"""Short-query admission checks, with semantic execution explicitly disabled."""
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from utils.search import normalize_query, normalized_words, search_memes


class ShortSearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.memes = json.loads((Path(__file__).resolve().parents[1] / "data/memes.json").read_text())

    def setUp(self):
        provider = patch("utils.semantic.semantic_scores", side_effect=AssertionError("Model must not run"))
        self.provider = provider.start()
        self.addCleanup(provider.stop)
        self.addCleanup(self.provider.assert_not_called)

    def names(self, query):
        return [r["name"] for r in search_memes(self.memes, query)]

    def test_people_have_explicit_evidence(self):
        self.assertEqual(set(self.names("man")), {"Distracted Boyfriend", "Stonks", "Hide the Pain Harold"})
        self.assertEqual(set(self.names("woman")), {"Woman Yelling at a Cat", "First World Problems", "Distracted Boyfriend"})
        self.assertIn("Ancient Aliens", self.names("guy"))
        self.assertIn("Disaster Girl", self.names("girl"))

    def test_irregular_people_plurals_match_singular_order(self):
        for plural, singular in [("women", "woman"), ("men", "man"),
                                 ("crying women", "crying woman"), ("older men", "older man")]:
            with self.subTest(query=plural):
                self.assertTrue(self.names(singular))
                self.assertEqual(self.names(plural), self.names(singular))

    def test_irregular_normalization_is_whole_token_and_bidirectional(self):
        self.assertEqual(normalize_query("WOMEN, men! menu womenhood"),
                         "woman, man! menu womenhood")
        self.assertEqual(normalized_words("WOMEN men 2 womenhood menu"),
                         ["woman", "man", "two", "womenhood", "menu"])
        for singular, plural in [("woman", "women"), ("man", "men")]:
            strong = {"name": "Example", "keywords": [plural]}
            weak = {"name": "Other", "description": "Some " + plural + " are visible nearby"}
            self.assertEqual(search_memes([weak, strong], singular), [strong])
            self.assertEqual(search_memes([weak, strong], plural), [strong])

    def test_hybrid_fallback_receives_canonical_query(self):
        with patch("utils.search.semantic_fallback", return_value=[]) as fallback:
            search_memes([], "women exploring a distant lunar observatory")
            fallback.assert_called_once_with([], "woman exploring a distant lunar observatory")

    def test_representative_short_searches(self):
        cases = {
            "cat": "Woman Yelling at a Cat", "dog": "This Is Fine",
            "work": "Boardroom Meeting Suggestion", "money": "Stonks",
            "angry": "Woman Yelling at a Cat", "confused": "Confused Nick Young",
            "choice": "Two Buttons", "success": "Success Kid", "stress": "Two Buttons",
            "reaction": "Monkey Puppet", "relationship": "Distracted Boyfriend",
            "fire": "This Is Fine", "crying": "First World Problems", "smile": "Hide the Pain Harold",
            "drake": "Drake Hotline Bling", "coffee": "Hide the Pain Harold",
            "space": "Always Has Been", "waiting": "Waiting Skeleton", "joy": "Success Kid",
            "handshake": "Epic Handshake", "side eye": "Monkey Puppet",
            "burning room": "This Is Fine", "older man": "Hide the Pain Harold",
            "crying woman": "First World Problems", "meme man": "Stonks", "button guy": "Two Buttons",
        }
        for query, expected in cases.items():
            with self.subTest(query=query):
                self.assertIn(expected, self.names(query))

    def test_dataset_short_items_find_their_owner(self):
        for meme in self.memes:
            for field in ("name", "aliases", "keywords", "emotions", "categories"):
                values = meme[field] if isinstance(meme[field], list) else [meme[field]]
                for value in values:
                    if len(value.split()) <= 2:
                        with self.subTest(query=value, owner=meme["name"]):
                            self.assertIn(meme["name"], self.names(value))

    def test_noisy_or_unrepresented_terms(self):
        for query in ["person", "couple", "sad", "happy", "laptop", "gray", "suited", "red",
                      "purple", "zxqv", "zxqv jklz", "quantum spaceship"]:
            with self.subTest(query=query):
                self.assertEqual(self.names(query), [])

    def test_exact_corpus_term_does_not_admit_fuzzy_noise(self):
        self.assertEqual(self.names("money"), ["Stonks"])
        self.assertEqual(self.names("smile"), ["Hide the Pain Harold"])

    def test_admission_depends_on_fields_not_person_word_list(self):
        for word in ["pilot", "robot", "violin", "person"]:
            for field in ["name", "aliases", "keywords", "situations", "categories", "emotions"]:
                with self.subTest(word=word, field=field):
                    strong = {"name": "Example", field: [word]}
                    if field == "name":
                        strong[field] = word
                    weak = {"name": "Other", "description": "A " + word + " is visible nearby"}
                    self.assertEqual(search_memes([weak, strong], word), [strong])

    def test_two_words_need_an_explicit_anchor(self):
        weak = {"name": "Other", "description": "A blue violin is visible"}
        strong = {"name": "Example", "keywords": ["violin"], "description": "A blue violin is visible"}
        self.assertEqual(search_memes([weak, strong], "blue violin"), [strong])

    def test_selective_meaning_and_repeated_incidental_prose(self):
        memes = [{"name": str(i), "meaning": "A person waits"} for i in range(20)]
        memes[0]["meaning"] += " feeling angry"
        self.assertEqual(search_memes(memes, "angry"), [memes[0]])
        self.assertEqual(search_memes(memes, "person"), [])

    def test_core_typo_and_number_regressions(self):
        self.assertEqual(self.names("Dittaced boyfrien")[0], "Distracted Boyfriend")
        self.assertEqual(self.names("2 choices"), self.names("two choices"))
        self.assertEqual(self.names("2 choices")[0], "Two Buttons")


if __name__ == "__main__":
    unittest.main()
