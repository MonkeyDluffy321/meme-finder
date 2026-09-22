from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from utils.meme_search import search_finished_memes
from utils.search import search_memes


def record(identity, caption, **extra):
    return dict(meme_id=identity, caption_text=caption, provider="fixture",
                image_url=f"https://example.org/{identity}.png", **extra)


class FinishedMemeSearchTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / "instances.json"
        self.rows = [
            record("food", "Pizza or tacos?", template_id="two-buttons", template_name="Two Buttons",
                   topics=["pizza", "taco", "choice"], situation="Can't decide what to eat"),
            record("doubt", "Planting seeds of doubt", topics=["uncertainty"], situation="Making someone question their confidence"),
            record("sleep", "Sleep or another episode?", template_id="two-buttons", template_name="Two Buttons",
                   topics=["choice", "television"], situation="Can't decide whether to sleep"),
            record("garden", "Watering my plants", topics=["seeds", "gardening"], source_confidence="verified"),
        ]
        self.write()

    def write(self):
        self.path.write_text(json.dumps({"version": 1, "records": self.rows}), encoding="utf-8")

    def search(self, query, **kwargs):
        return search_finished_memes(query, index_path=self.path, **kwargs)

    def test_exact_caption_first_without_template(self):
        result = self.search("PLANTING seeds of doubt")
        self.assertEqual(result[0]["meme_id"], "doubt")
        self.assertEqual(result[0]["template_id"], "")

    def test_partial_caption_and_topics(self):
        self.assertEqual(self.search("seeds doubt")[0]["meme_id"], "doubt")
        self.assertEqual(self.search("pizza taco choice")[0]["meme_id"], "food")
        self.assertEqual(self.search("uncertainty")[0]["meme_id"], "doubt")

    def test_descriptive_situation_query(self):
        self.assertEqual(self.search("can't decide what to eat")[0]["meme_id"], "food")
        self.assertEqual(self.search("someone question confidence")[0]["meme_id"], "doubt")

    def test_same_template_variants_and_soft_copies_remain(self):
        self.assertEqual({r["meme_id"] for r in self.search("two buttons")}, {"food", "sleep"})
        self.rows[0]["perceptual_hash"] = "01" * 128
        self.rows.append({**self.rows[0], "meme_id": "soft", "image_url": "https://mirror.example/food.jpg"})
        self.write()
        result = self.search("pizza")
        self.assertEqual([r["meme_id"] for r in result], ["food", "soft"])

    def test_exact_copies_collapse_and_alternate_caption_is_searchable(self):
        self.rows[0]["image_sha256"] = "a" * 64
        for number in range(3):
            self.rows.append({**self.rows[0], "provider": f"mirror-{number}",
                              "image_url": f"https://mirror.example/{number}.png",
                              "caption_text": "Pizza versus tacos"})
        self.write()
        result = self.search("Pizza versus tacos")
        self.assertEqual(len(result), 1)
        self.assertEqual(len(result[0]["provenance"]), 4)

    def test_empty_nonsense_and_incidental_overlap(self):
        for query in ("", "  ", "!!!", "the meme", "zzqxvv", "pizza zzqxvv", None, "x" * 5001):
            self.assertEqual(self.search(query), [], query)
        self.assertEqual(self.search("pizza", limit=0), [])

    def test_confidence_only_breaks_relevance_ties(self):
        self.rows = [record("a", "Lunch break", source_confidence="unknown"),
                     record("b", "Lunch break", source_confidence="verified"),
                     record("c", "Something else", topics=["lunch", "break"], source_confidence="verified")]
        self.write()
        self.assertEqual([r["meme_id"] for r in self.search("lunch break")], ["b", "a", "c"])

    def test_deterministic_fresh_results_and_offline(self):
        with patch("socket.socket.connect") as network, patch("utils.semantic.get_embedding_model") as model:
            first = self.search("choice")
            self.assertEqual(first, self.search("choice"))
            first[0]["topics"].append("mutated")
            self.assertNotIn("mutated", self.search("choice")[0]["topics"])
            network.assert_not_called()
            model.assert_not_called()
        self.assertEqual(len(self.search("choice", limit=1)), 1)

    def test_malformed_index_safe(self):
        self.path.write_text("bad json", encoding="utf-8")
        self.assertEqual(self.search("pizza"), [])

    def test_v3_template_search_is_unchanged(self):
        catalog = json.loads((Path(__file__).resolve().parents[1] / "data/memes.json").read_text(encoding="utf-8"))
        original = deepcopy(catalog)
        queries = ("distracted boyfriend", "2 choices", "painful forced smile", "nonsensezz")
        before = [search_memes(catalog, q, use_semantic=False) for q in queries]
        with patch("utils.search.search_memes", side_effect=AssertionError("No template ranking")):
            self.search("pizza")
        self.assertEqual(before, [search_memes(catalog, q, use_semantic=False) for q in queries])
        self.assertEqual(catalog, original)
