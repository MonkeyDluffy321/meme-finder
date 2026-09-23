from io import BytesIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

from utils.meme_ingestion import ingest_memes, normalize_provider_record
from utils.meme_index import load_index
from utils.meme_search import search_finished_memes


def record(**changes):
    return dict(dict(id=12, text="Weekend waffles", tags=["Food", " FOOD "],
                     image_url="https://example.org/meme.png",
                     source_page="https://example.org/posts/12"), **changes)


class FixtureProvider:
    def __init__(self, name="fixture", rows=None):
        self.name = name
        self.rows = rows if rows is not None else [record()]

    def records(self):
        return iter(self.rows)


def image_bytes(color):
    buffer = BytesIO()
    Image.new("RGB", (32, 32), color).save(buffer, format="PNG")
    return buffer.getvalue()


class IngestionTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / "instances.json"
        network = patch("socket.socket.connect", side_effect=AssertionError("No network"))
        self.network = network.start()
        self.addCleanup(network.stop)

    def ingest(self, providers):
        return ingest_memes(providers, index_path=self.path)

    def test_normalization_and_unknown_optional_template(self):
        row = normalize_provider_record(record(description="Breakfast time"), " Fixture ")
        self.assertEqual(row["meme_id"], "12")
        self.assertEqual(row["provider"], "fixture")
        self.assertEqual(row["topics"], ["food"])
        self.assertEqual(row["caption_text"], "Weekend waffles")
        self.assertEqual(row["situation"], "Breakfast time")
        self.assertEqual((row["template_id"], row["language"]), ("", "und"))
        self.assertEqual(normalize_provider_record(record(template_id="unknown"), "a")["template_id"], "unknown")
        raw = record()
        del raw["id"]
        self.assertEqual(normalize_provider_record(raw, "a"), normalize_provider_record(raw, "a"))
        self.assertTrue(normalize_provider_record(raw, "a")["meme_id"].startswith("generated-"))

    def test_valid_ingestion_and_existing_search(self):
        report = self.ingest(FixtureProvider())
        self.assertEqual((report["received"], report["accepted"], report["added"]), (1, 1, 1))
        self.assertTrue(report["written"])
        self.assertEqual(search_finished_memes("Weekend waffles", index_path=self.path)[0]["meme_id"], "12")
        self.network.assert_not_called()

    def test_strong_language_boolean_is_persisted_and_loaded(self):
        rows = [record(id="strong", text="Shit happens"),
                record(id="normal", text="Weekend waffles")]
        report = self.ingest(FixtureProvider(rows=rows))
        self.assertEqual(report["accepted"], 2)
        for records in (json.loads(self.path.read_text(encoding="utf-8"))["records"], load_index(self.path)):
            indexed = {row["meme_id"]: row for row in records}
            self.assertIs(indexed["strong"]["contains_strong_language"], True)
            self.assertIs(indexed["normal"]["contains_strong_language"], False)
            self.assertEqual(indexed["strong"]["caption_text"], "Shit happens")

    def test_nonboolean_quality_flag_is_not_assigned(self):
        with patch("utils.meme_ingestion.caption_quality", return_value=(None, None)):
            report = self.ingest(FixtureProvider())
        self.assertEqual(report["accepted"], 1)
        self.assertNotIn("contains_strong_language", json.loads(self.path.read_text(encoding="utf-8"))["records"][0])

    def test_multiple_providers_provenance_and_exact_duplicates_survive_reload(self):
        data = image_bytes("red")
        providers = [FixtureProvider("one", [record(image_bytes=data)]),
                     FixtureProvider("two", [record(id="other", text="Alternate transcription",
                        image_url="https://mirror.example/image.png", image_bytes=data)])]
        report = self.ingest(providers)
        self.assertEqual((report["accepted"], report["duplicates"], report["index_size"]), (2, 1, 1))
        row = load_index(self.path)[0]
        self.assertEqual({p["provider"] for p in row["provenance"]}, {"one", "two"})
        self.assertEqual({p["meme_id"] for p in row["provenance"]}, {"12", "other"})
        self.assertTrue(all(p["source_page"] and p["image_url"] for p in row["provenance"]))
        self.assertEqual(set(row["caption_variants"]), {"Weekend waffles", "Alternate transcription"})
        before = self.path.read_bytes()
        repeat = self.ingest(list(reversed(providers)))
        self.assertEqual(repeat["duplicates"], 2)
        self.assertFalse(repeat["written"])
        self.assertEqual(before, self.path.read_bytes())
        self.assertEqual(len(search_finished_memes("Alternate transcription", index_path=self.path)), 1)

    def test_same_template_and_reused_url_different_images_retained(self):
        rows = [record(template_id="same", image_bytes=image_bytes("red")),
                record(template_id="same", image_bytes=image_bytes("blue")),
                record(template_id="same", text="Monday misery")]
        self.assertEqual(self.ingest(FixtureProvider(rows=rows))["index_size"], 3)

    def test_untrusted_hash_claims_cannot_merge_different_urls(self):
        rows = [record(image_sha256="a" * 64),
                record(image_sha256="a" * 64, image_url="https://example.org/other.png")]
        self.assertEqual(self.ingest(FixtureProvider(rows=rows))["index_size"], 2)

    def test_malformed_records_and_provider_failure_are_isolated(self):
        class Broken:
            name = "broken"

            def records(self):
                yield record(text="Good partial record")
                raise RuntimeError("private provider error")

        bad = [None, {}, [], record(image_url=None), record(image_url=False),
               record(source_page=[]), record(text=7), record(tags="food"),
               record(id=False), record(image_bytes=b"broken"), record(image_url="file:///secret")]
        report = self.ingest([FixtureProvider(rows=bad), Broken(), FixtureProvider()])
        self.assertEqual(report["invalid"], len(bad))
        self.assertEqual(report["accepted"], 2)
        self.assertEqual(report["index_size"], 2)
        self.assertEqual(len(report["errors"]), 2)
        self.assertNotIn("private provider error", str(report))

    def test_identical_sources_collapse_and_order_is_deterministic(self):
        first = FixtureProvider("a", [record(), record()])
        second = FixtureProvider("b", [record(text="Monday misery")])
        report = self.ingest([first, second])
        self.assertEqual(report["duplicates"], 1)
        before = self.path.read_bytes()
        other = self.path.with_name("other.json")
        ingest_memes([second, first], index_path=other)
        self.assertEqual(before, other.read_bytes())
        self.assertEqual(self.ingest([second, first])["added"], 0)
        self.assertEqual(before, self.path.read_bytes())

    def test_corrupt_existing_index_and_failed_write_preserve_disk(self):
        self.path.write_text("broken", encoding="utf-8")
        with self.assertRaises(ValueError):
            self.ingest(FixtureProvider())
        self.assertEqual(self.path.read_text(), "broken")
        self.path.unlink()
        self.ingest(FixtureProvider())
        before = self.path.read_bytes()
        with patch("utils.importer.os.replace", side_effect=OSError("disk error")), self.assertRaises(OSError):
            self.ingest(FixtureProvider(rows=[record(text="New caption")]))
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(list(self.path.parent.glob("*.lock")), [])
        self.assertEqual(list(self.path.parent.glob("*.tmp")), [])

    def test_limits_and_concurrent_writer_do_not_replace_index(self):
        self.ingest(FixtureProvider())
        before = self.path.read_bytes()
        with patch("utils.meme_ingestion.MAX_INDEX_BYTES", len(before) + 1), self.assertRaises(ValueError):
            self.ingest(FixtureProvider(rows=[record(text="New caption")]))
        self.assertEqual(self.path.read_bytes(), before)
        lock = self.path.with_name(self.path.name + ".lock")
        lock.touch()
        with self.assertRaises(FileExistsError):
            self.ingest(FixtureProvider())
        self.assertTrue(lock.exists())
        self.assertEqual(self.path.read_bytes(), before)

    def test_empty_import_does_not_create_index(self):
        self.assertFalse(self.ingest(FixtureProvider(rows=[{}]))["written"])
        self.assertFalse(self.path.exists())

    def test_provider_iterator_bounded(self):
        class Endless:
            name = "fixture"

            def records(self):
                while True:
                    yield record()

        with patch("utils.meme_ingestion.MAX_RECORDS", 2):
            report = self.ingest(Endless())
        self.assertEqual(report["received"], 2)
        self.assertTrue(report["errors"])
