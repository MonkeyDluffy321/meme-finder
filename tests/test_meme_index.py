from copy import deepcopy
from io import BytesIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

from utils.meme_index import clean_records, image_fingerprints, load_index, normalize_record
from utils.search import search_memes


def record(**changes):
    return dict(dict(meme_id="weekend-1", provider="sample", caption_text="Expectation: rest\nReality: work",
                     topics=["Work"], situation="Working on weekends", language="en",
                     image_url="https://example.org/memes/weekend.png",
                     source_page="https://example.org/posts/weekend"), **changes)


class MemeIndexTests(unittest.TestCase):
    def test_valid_record_and_no_template_required(self):
        row = normalize_record(record())
        self.assertEqual(row["kind"], "finished_meme")
        self.assertEqual(row["template_id"], "")
        self.assertEqual(row["topics"], ["work"])
        self.assertEqual(row["source_confidence"], "unknown")
        self.assertEqual(normalize_record(record(template_id="choice"))["template_id"], "choice")

    def test_caption_normalization_retains_meaningful_differences(self):
        row = normalize_record(record(caption_text="  ＷＯＲＫ\n  Isn't  FUN!  ", normalized_caption="untrusted"))
        self.assertEqual(row["normalized_caption"], "work isn't fun!")
        self.assertNotEqual(row["normalized_caption"], normalize_record(record(caption_text="Work is fun!"))["normalized_caption"])

    def test_malformed_records_are_skipped(self):
        bad = [None, [], {}, record(caption_text=123), record(topics="work"), record(provider=""),
               record(image_url="file:///private"), record(image_url="http://127.0.0.1/x"),
               record(image_sha256="bad"), record(source_confidence=[]), record(caption_text="x" * 5001)]
        self.assertEqual(len(clean_records(bad + [record()])), 1)

    def test_exact_cross_provider_copies_collapse_with_provenance(self):
        original = record(image_sha256="a" * 64)
        mirror = record(provider="mirror", meme_id="different", image_url="https://mirror.example/meme.jpg", image_sha256="a" * 64)
        before = deepcopy([original, mirror])
        rows = clean_records([original, mirror])
        self.assertEqual(len(rows), 1)
        self.assertEqual(len(rows[0]["provenance"]), 2)
        self.assertEqual([original, mirror], before)
        self.assertEqual(len(clean_records([record(), record()])), 1)

    def test_same_template_and_meaningful_caption_variations_survive(self):
        rows = clean_records([record(template_id="choice", perceptual_hash="01" * 128),
                              record(template_id="choice", caption_text="Expectation: work\nReality: rest",
                                     perceptual_hash="01" * 128)])
        self.assertEqual(len(rows), 2)
        self.assertNotIn("possible_duplicate_of", rows[1])
        # A reused URL is not stronger evidence than different image content.
        self.assertEqual(len(clean_records([record(image_sha256="a" * 64),
                                            record(image_sha256="b" * 64)])), 2)

    def test_perceptual_copies_are_soft_duplicates_not_removed(self):
        rows = clean_records([record(perceptual_hash="01" * 128),
                              record(provider="mirror", image_url="https://mirror.example/resized.jpg",
                                     perceptual_hash="01" * 128)])
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1]["possible_duplicate_of"], rows[0]["instance_key"])

    def test_provider_independence_and_equal_captions_do_not_merge(self):
        rows = clean_records([record(), record(provider="another", image_url="https://other.example/reaction.png")])
        self.assertEqual(len(rows), 2)
        self.assertNotEqual(rows[0]["instance_key"], rows[1]["instance_key"])

    def test_provider_iterator_is_bounded(self):
        class Provider:
            def records(self):
                yield record()
                raise AssertionError("Must stop at the record limit")

        with patch("utils.meme_index.MAX_RECORDS", 1):
            self.assertEqual(len(clean_records(Provider().records())), 1)
        self.assertEqual(clean_records(None), [])

    def test_local_hashes_detect_reencoded_pixels(self):
        image = Image.new("RGB", (64, 64), "red")
        first, second = BytesIO(), BytesIO()
        image.save(first, format="PNG", compress_level=0)
        image.save(second, format="PNG", compress_level=9)
        a, b = image_fingerprints(first.getvalue()), image_fingerprints(second.getvalue())
        self.assertNotEqual(a["image_sha256"], b["image_sha256"])
        self.assertEqual(a["pixel_sha256"], b["pixel_sha256"])
        self.assertEqual(len(clean_records([record(**a), record(provider="mirror", image_url="https://mirror.example/a.png", **b)])), 1)

    def test_loading_is_safe_bounded_and_offline(self):
        with tempfile.TemporaryDirectory() as directory, patch("socket.socket.connect") as network:
            path = Path(directory) / "instances.json"
            self.assertEqual(load_index(path), [])
            for payload in ("bad json", "[]", '{"version": 2, "records": []}',
                            json.dumps({"version": 1, "records": [None, record()]})):
                path.write_text(payload, encoding="utf-8")
                self.assertEqual(len(load_index(path)), 1 if "weekend-1" in payload else 0)
            with patch("utils.meme_index.MAX_INDEX_BYTES", 10):
                self.assertEqual(load_index(path), [])
            network.assert_not_called()

    def test_finished_index_does_not_change_v3_template_search(self):
        catalog = json.loads((Path(__file__).resolve().parents[1] / "data" / "memes.json").read_text(encoding="utf-8"))
        queries = ("distracted boyfriend", "2 choices", "painful forced smile", "nonsensezz")
        before = [[row["id"] for row in search_memes(catalog, query, use_semantic=False)] for query in queries]
        with patch("utils.search.search_memes", side_effect=AssertionError("Index must not rank templates")):
            clean_records([record(), record(caption_text="2 choices")])
            self.assertEqual(load_index(), [])
        after = [[row["id"] for row in search_memes(catalog, query, use_semantic=False)] for query in queries]
        self.assertEqual(before, after)
