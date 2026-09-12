import copy
import json
from pathlib import Path
import unittest

from utils.search import search_memes


def record(name="", keywords=None, meaning="", description=""):
    return dict(name=name, keywords=keywords or [], meaning=meaning,
                description=description)


class SearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = Path(__file__).resolve().parents[1] / "data" / "memes.json"
        cls.memes = json.loads(path.read_text(encoding="utf-8"))

    def test_requested_searches(self):
        cases = {
            "distracted boyfriend": "Distracted Boyfriend",
            "distrcted boyfriend": "Distracted Boyfriend",
            "distrcted": "Distracted Boyfriend",
            "burning room": "This Is Fine",
            "two choices": "Two Buttons",
            "2 choices": "Two Buttons",
            "DISTRACTED, BOYFRIEND!": "Distracted Boyfriend",
        }
        for query, expected in cases.items():
            with self.subTest(query=query):
                results = search_memes(self.memes, query)
                self.assertTrue(results)
                self.assertEqual(results[0]["name"], expected)

    def test_choices_ranking_and_numeric_equivalence(self):
        words = search_memes(self.memes, "two choices")
        digits = search_memes(self.memes, "2 choices")
        self.assertEqual(digits, words)
        names = [meme["name"] for meme in words]
        self.assertEqual(names[0], "Two Buttons")
        self.assertIn("Drake Hotline Bling", names)
        self.assertLess(names.index("Two Buttons"), names.index("Drake Hotline Bling"))

    def test_numbers_zero_through_twenty(self):
        words = "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty".split()
        for number, word in enumerate(words):
            with self.subTest(number=number):
                written = record(name=word)
                numeric = record(name=str(number))
                self.assertEqual(search_memes([written], str(number)), [written])
                self.assertEqual(search_memes([numeric], word), [numeric])

    def test_numeric_phrase_bonus(self):
        records = [record(name="buttons two"), record(name="2 buttons")]
        for query in ["two buttons", "2 buttons"]:
            self.assertEqual(search_memes(records, query), records[::-1])

    def test_numbers_are_not_fuzzy_matched(self):
        for query, name in [("16", "sixteenx"), ("sixteenx", "16"),
                            ("sixteen", "fifteen"), ("12345", "123456"),
                            ("123456", "12345")]:
            with self.subTest(query=query, name=name):
                self.assertEqual(search_memes([record(name=name)], query), [])

    def test_unrelated_queries(self):
        for query in ["zxqv jklz", "quantum spaceship", "boyfriend zxqv jklz"]:
            with self.subTest(query=query):
                self.assertEqual(search_memes(self.memes, query), [])

    def test_blank_returns_all_in_original_order(self):
        for query in ["", " \t\n"]:
            results = search_memes(self.memes, query)
            self.assertEqual(results, self.memes)
            self.assertIsNot(results, self.memes)
            for actual, original in zip(results, self.memes):
                self.assertIs(actual, original)

    def test_stop_words_and_punctuation(self):
        for query in ["the and with", "!!! ...", "THE, AND!!!"]:
            self.assertEqual(search_memes(self.memes, query), [])

    def test_field_priority(self):
        records = [record(description="celebration"), record(meaning="celebration"),
                   record(keywords=["celebration"]), record(name="celebration")]
        self.assertEqual(search_memes(records, "celebration"), records[::-1])

    def test_phrase_bonus_and_normalization(self):
        records = [record(name="room burning"), record(name="burning room")]
        self.assertEqual(search_memes(records, "BURNING,   ROOM!"), records[::-1])

    def test_no_phrase_across_keywords(self):
        records = [record(keywords=["burning", "room"]),
                   record(keywords=["burning room"])]
        self.assertEqual(search_memes(records, "burning room"), records[::-1])

    def test_short_words_require_exact_match(self):
        for query in ["cot", "do", "fir"]:
            self.assertEqual(search_memes([record(name="cat dog fire")], query), [])
        self.assertTrue(search_memes([record(name="cat")], "cat"))

    def test_single_weak_fuzzy_match_rejected(self):
        self.assertEqual(search_memes([record(name="planet")], "planer"), [])
        self.assertEqual(search_memes([record(name="choices")], "choicex"), [])

    def test_exact_beats_fuzzy_in_same_field(self):
        records = [record(name="distracted"), record(name="distrcted")]
        self.assertEqual(search_memes(records, "distrcted"), records[::-1])

    def test_identity_no_mutation_and_stable_ties(self):
        records = [record(name="cat"), record(name="cat")]
        before = copy.deepcopy(records)
        results = search_memes(records, "cat")
        self.assertEqual(records, before)
        self.assertIs(results[0], records[0])
        self.assertIs(results[1], records[1])

    def test_empty_collection(self):
        self.assertEqual(search_memes([], "cat"), [])


if __name__ == "__main__":
    unittest.main()
