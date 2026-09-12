import json
import unittest
from pathlib import Path

from utils.search import search_memes


DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "memes.json"


class Step5ASearchRegressionTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.memes = json.loads(
            DATA_PATH.read_text(encoding="utf-8")
        )

    def names_for(self, query):
        return [
            meme["name"]
            for meme in search_memes(self.memes, query)
        ]

    def test_full_name_typo_recovery(self):
        names = self.names_for("Dittaced boyfrien")

        self.assertTrue(names)
        self.assertEqual(names[0], "Distracted Boyfriend")

    def test_numeric_choice_query(self):
        names = self.names_for("2 choices")

        self.assertGreaterEqual(len(names), 1)
        self.assertEqual(names[0], "Two Buttons")

        if "Drake Hotline Bling" in names:
            self.assertLess(
                names.index("Two Buttons"),
                names.index("Drake Hotline Bling"),
            )

    def test_word_choice_query(self):
        names = self.names_for("two choices")

        self.assertGreaterEqual(len(names), 1)
        self.assertEqual(names[0], "Two Buttons")

    def test_descriptive_distracted_boyfriend_query(self):
        names = self.names_for(
            "guy distracted by another woman"
        )

        self.assertTrue(names)
        self.assertEqual(names[0], "Distracted Boyfriend")

    def test_this_is_fine_descriptive_query(self):
        names = self.names_for(
            "pretending everything is okay during chaos"
        )

        self.assertTrue(names)
        self.assertEqual(names[0], "This Is Fine")

    def test_hide_the_pain_descriptive_query(self):
        names = self.names_for("painful forced smile")

        self.assertTrue(names)
        self.assertEqual(names[0], "Hide the Pain Harold")

    def test_two_buttons_descriptive_query(self):
        names = self.names_for(
            "choosing between two bad options"
        )

        self.assertTrue(names)
        self.assertEqual(names[0], "Two Buttons")

    def test_man_requires_explicit_metadata(self):
        names = self.names_for("man")

        self.assertEqual(set(names), {"Distracted Boyfriend", "Stonks", "Hide the Pain Harold"})

    def test_random_nonsense_is_rejected(self):
        names = self.names_for("zxqv jklz")

        self.assertEqual(names, [])

    def test_unrelated_query_is_rejected(self):
        names = self.names_for("quantum spaceship")

        self.assertEqual(names, [])

    def test_useful_single_word_search_still_works(self):
        names = self.names_for("drake")

        self.assertTrue(names)
        self.assertEqual(names[0], "Drake Hotline Bling")


if __name__ == "__main__":
    unittest.main()
