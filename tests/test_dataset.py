import json
from pathlib import Path
import unittest


TEXT_FIELDS = {"id", "name", "meaning", "description", "image_url"}
LIST_FIELDS = {"aliases", "keywords", "situations", "emotions", "categories"}


class DatasetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = Path(__file__).resolve().parents[1] / "data" / "memes.json"
        cls.memes = json.loads(path.read_text(encoding="utf-8"))

    def test_collection_size(self):
        self.assertIsInstance(self.memes, list)
        self.assertGreaterEqual(len(self.memes), 40)

    def test_required_fields(self):
        for index, meme in enumerate(self.memes):
            with self.subTest(index=index):
                self.assertIsInstance(meme, dict)
                self.assertTrue((TEXT_FIELDS | LIST_FIELDS) <= meme.keys())

    def test_unique_ids(self):
        ids = [meme["id"] for meme in self.memes]
        self.assertEqual(len(ids), len(set(ids)))

    def test_unique_names(self):
        names = [meme["name"].strip().casefold() for meme in self.memes]
        self.assertEqual(len(names), len(set(names)))

    def test_unique_image_urls(self):
        urls = [meme["image_url"] for meme in self.memes]
        self.assertEqual(len(urls), len(set(urls)))

    def test_image_url_scheme(self):
        for meme in self.memes:
            with self.subTest(name=meme["name"]):
                self.assertTrue(meme["image_url"].startswith(("http://", "https://")))

    def test_kebab_case_ids(self):
        for meme in self.memes:
            with self.subTest(name=meme["name"]):
                self.assertRegex(meme["id"], r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

    def test_nonempty_text(self):
        for meme in self.memes:
            for field in TEXT_FIELDS:
                with self.subTest(name=meme.get("name"), field=field):
                    self.assertIsInstance(meme[field], str)
                    self.assertTrue(meme[field].strip())

    def test_string_lists(self):
        for meme in self.memes:
            for field in LIST_FIELDS:
                with self.subTest(name=meme["name"], field=field):
                    self.assertIsInstance(meme[field], list)
                    self.assertTrue(meme[field])
                    for value in meme[field]:
                        self.assertIsInstance(value, str)
                        self.assertTrue(value.strip())


if __name__ == "__main__":
    unittest.main()
