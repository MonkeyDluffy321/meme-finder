from io import BytesIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

from utils.meme_quality import caption_quality
from utils.meme_ingestion import ingest_memes
from utils.meme_index import load_index
from utils.meme_search import search_finished_memes
from utils.meme_sources import genmymeme_record


class Provider:
    name = "fixture"

    def __init__(self, rows):
        self.rows = rows

    def records(self):
        yield from self.rows


def record(caption, **extra):
    return dict(dict(id="one", caption=caption, image_url="https://example.org/meme.png",
                     source_page="https://example.org/post/one"), **extra)


class QualityTests(unittest.TestCase):
    def test_honda_civic_live_caption_regression(self):
        # Exact caption from preview record cfbc9668816e89394a6f991e.
        caption = "2006 Honda Civic\n2006 Honda Civic\n2006 Honda Civic\n2006 Honda Civic\n2006 Honda Civic\n67"
        self.assertEqual(caption_quality(caption), ("repetitive_spam", False))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "index.json"
            report = ingest_memes(Provider([record(caption), record("Shit happens", id="two", template_id="unknown")]), index_path=path)
            self.assertEqual(report["skip_reasons"], {"repetitive_spam": 1})
            self.assertEqual(report["accepted"], 1)
            row = load_index(path)[0]
            self.assertEqual(row["template_id"], "unknown")
            self.assertTrue(row["contains_strong_language"])
            self.assertEqual(search_finished_memes("Shit happens", index_path=path)[0]["meme_id"], "two")

    def test_dominant_phrase_and_near_identical_repetition(self):
        for caption in ("2006 Honda Civic " * 5 + "67", "buy this thing " * 20 + "now",
                        "another pointless repeated line\n" * 9 + "42",
                        "\n".join(f"{year} HONDA civic!!!" for year in range(2001, 2007)),
                        "2006 Honda Civic!\n2006 HONDA civic?\n2006 Honda Civic.\n2006 Honda Civic\n2006 Honda Civic\n67"):
            with self.subTest(caption=caption):
                self.assertEqual(caption_quality(caption)[0], "repetitive_spam")

    def test_normal_emphasis_and_varied_lines_remain_valid(self):
        for caption in ("no no no", "wait wait wait", "2006 Honda Civic\n2006 Honda Civic\n67",
                        "I cannot believe this is happening again\n" * 2,
                        "I cannot believe this is happening again\n" * 3,
                        "fuck this\nfuck this", "Shit happens", "bruh", "F",
                        "My hopes died on Monday", "My dating life is a disaster",
                        "I want coffee\nI want sleep\nI want holidays\nI want cake\nI want peace",
                        "2006 Honda Civic " * 5 + "but the real joke is that my car is actually a bicycle"):
            with self.subTest(caption=caption):
                self.assertIsNone(caption_quality(caption)[0])

    def test_conservative_acceptance(self):
        for caption in ("Weekend waffles", "No", "F", "42", "bruh", "💀", "???", "...",
                        "你好", "नहीं", "لا", "NO\nNO\nNO", "ha " * 5,
                        "fuck you", "This is fucking fine", "Shit happens", "bullshit",
                        "My hopes died on Monday", "Sex education matters", "chicken breast",
                        "Scunthorpe", "CLASSIC", "AAAAAAAAAA", "why 😭😭😭"):
            with self.subTest(caption=caption):
                self.assertIsNone(caption_quality(caption)[0])

    def test_skip_reasons(self):
        cases = [("", "empty_caption"), (" \n\u200b\ufeff", "empty_caption"),
                 (None, "malformed_caption"), (123, "malformed_caption"),
                 ("hello\x00world", "malformed_caption"), ("x\ud800", "malformed_caption"),
                 ("a" * 5001, "malformed_caption"), ("spam " * 30, "repetitive_spam"),
                 ("click my profile\n" * 10, "repetitive_spam"),
                 ("buy now " * 30, "repetitive_spam"),
                 ("\ufffd" * 10, "garbled_text"), ("Ã©Ã©Ã©Ã©", "garbled_text"),
                 ("---------", "low_information"), ("https://example.org", "low_information"),
                 ("[object Object]", "low_information"), ("send nudes", "unsafe_adult_content"),
                 ("watch hardcore porn", "unsafe_adult_content"), ("a blowjob", "unsafe_adult_content"),
                 ("sucking his cock", "unsafe_adult_content"), ("nude photos", "unsafe_adult_content")]
        for caption, reason in cases:
            with self.subTest(reason=reason, caption=repr(caption)):
                self.assertEqual(caption_quality(caption)[0], reason)

    def test_flags_are_deterministic_and_not_rejection(self):
        for text, expected in (("oh shit", True), ("fucking Monday", True), ("class", False), ("No", False)):
            self.assertEqual(caption_quality(text), (None, expected))
            self.assertEqual(caption_quality(text), caption_quality(text))

    def test_ingestion_reporting_and_metadata(self):
        with tempfile.TemporaryDirectory() as directory, patch("socket.socket.connect", side_effect=AssertionError("offline")):
            path = Path(directory) / "index.json"
            rows = [record("Shit happens", template_name="Unknown template"), record(""),
                    record("spam " * 30), record("\ufffd" * 10), record("send nudes"),
                    record("hello\x00"), record("------")]
            report = ingest_memes(Provider(rows), index_path=path)
            self.assertEqual((report["accepted"], report["invalid"], report["quality_skipped"]), (1, 6, 6))
            self.assertEqual(set(report["skip_reasons"]), {"empty_caption", "repetitive_spam", "garbled_text",
                                                         "unsafe_adult_content", "malformed_caption", "low_information"})
            row = load_index(path)[0]
            self.assertTrue(row["contains_strong_language"])
            self.assertEqual(row["template_name"], "Unknown template")
            self.assertEqual(row["caption_text"], "Shit happens")
            self.assertEqual(row["provenance"][0]["source_page"], rows[0]["source_page"])
            self.assertEqual(row["provenance"][0]["meme_id"], "one")
            self.assertEqual(search_finished_memes("Shit happens", index_path=path)[0]["meme_id"], "one")
            before = path.read_bytes()
            self.assertFalse(ingest_memes(Provider(rows), index_path=path)["written"])
            self.assertEqual(path.read_bytes(), before)

    def test_caption_variants_provenance_and_flag_survive_deduplication(self):
        buffer = BytesIO()
        Image.new("RGB", (32, 32), "red").save(buffer, format="PNG")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "index.json"
            rows = [record("Monday happens", image_bytes=buffer.getvalue()),
                    record("Shit happens", provider="mirror", id="two", image_bytes=buffer.getvalue())]
            ingest_memes(Provider(rows), index_path=path)
            result = load_index(path)
            self.assertEqual(len(result), 1)
            self.assertEqual(set(result[0]["caption_variants"]), {"Monday happens", "Shit happens"})
            self.assertEqual({p["provider"] for p in result[0]["provenance"]}, {"fixture", "mirror"})
            self.assertTrue(result[0]["contains_strong_language"])
            ingest_memes(Provider([record("No", id="three")]), index_path=path)
            self.assertEqual(len(load_index(path)[0]["provenance"]), 2)

    def test_genmymeme_empty_caption_reports_shared_reason(self):
        row = genmymeme_record(dict(id="one", image_url="/memes/one.png", text_content='[{"text":" "}]'))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "index.json"
            report = ingest_memes(Provider([row]), index_path=path)
            self.assertEqual(report["skip_reasons"], {"empty_caption": 1})
            self.assertFalse(path.exists())

    def test_existing_rows_not_retroactively_filtered(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "index.json"
            old = dict(provider="legacy", meme_id="old", caption_text="", image_url="https://example.org/old.png")
            path.write_text(json.dumps({"version": 1, "records": [old]}))
            ingest_memes(Provider([record("No")]), index_path=path)
            self.assertEqual(len(load_index(path)), 2)
            self.assertNotIn("contains_strong_language", next(r for r in load_index(path) if r["meme_id"] == "old"))
