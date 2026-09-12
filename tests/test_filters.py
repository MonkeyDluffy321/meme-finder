import unittest

from utils.filters import filter_memes, filter_options


class FilterTests(unittest.TestCase):
    def setUp(self):
        self.memes = [
            {"categories": ["reaction", "conflict"], "emotions": ["anger"]},
            {"categories": ["reaction"], "emotions": ["joy"]},
            {"categories": ["choice"], "emotions": ["anger", "stress"]},
        ]

    def test_no_filters_preserves_order_and_identity(self):
        results = filter_memes(self.memes)
        self.assertEqual(results, self.memes)
        for original, result in zip(self.memes, results):
            self.assertIs(original, result)

    def test_any_tag_within_group(self):
        self.assertEqual(filter_memes(self.memes, ["conflict", "choice"]),
                         [self.memes[0], self.memes[2]])

    def test_both_groups_required(self):
        self.assertEqual(filter_memes(self.memes, ["reaction"], ["anger"]), [self.memes[0]])

    def test_emotion_only(self):
        self.assertEqual(filter_memes(self.memes, emotions=["joy", "stress"]), self.memes[1:])

    def test_excluded_results(self):
        self.assertEqual(filter_memes(self.memes, ["choice"], ["joy"]), [])

    def test_options_sorted_and_unique(self):
        self.assertEqual(filter_options(self.memes, "categories"), ["choice", "conflict", "reaction"])

    def test_empty_and_missing_metadata(self):
        self.assertEqual(filter_memes([], ["reaction"]), [])
        self.assertEqual(filter_memes([{}], ["reaction"]), [])
        self.assertEqual(filter_options([{}], "categories"), [])


if __name__ == "__main__":
    unittest.main()
