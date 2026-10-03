import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch, MagicMock
from io import BytesIO
from hashlib import sha256
from types import SimpleNamespace
from PIL import Image, ImageDraw

from utils.template_index import prepare_index, read_index, image_hash, informative
from utils.intelligence import analyze, reliable_template
from utils.identification import identify
from utils.ocr import OCRResult


class IndexTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cache = Path(self.tmp.name)
        self.memes = [{"id": "a", "image_url": "https://i.imgflip.com/a.jpg"}]
        image = Image.new("RGB", (80, 80), "white")
        ImageDraw.Draw(image).rectangle((0, 0, 40, 40), fill="black")
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        self.image, self.content = image, buffer.getvalue()

    def response(self):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = self.content
        return response

    def test_hash_and_blank_guard(self):
        self.assertEqual(len(image_hash(self.image)), 256)
        self.assertTrue(informative(self.image))
        self.assertFalse(informative(Image.new("RGB", (80, 80), "white")))

    def test_prepare_reuses_references_and_read_never_downloads(self):
        with patch("utils.template_index.urlopen", return_value=self.response()) as fetch:
            self.assertEqual(prepare_index(self.memes, use_embeddings=False, cache=self.cache), (1, False))
            self.assertEqual(prepare_index(self.memes, use_embeddings=False, cache=self.cache), (1, False))
            self.assertEqual(len(read_index(self.memes, self.cache)), 1)
            fetch.assert_called_once()

    def test_failed_download_and_model(self):
        with patch("utils.template_index.urlopen", side_effect=TimeoutError()):
            self.assertEqual(prepare_index(self.memes, cache=self.cache), (0, False))
        with patch("utils.template_index.urlopen", return_value=self.response()), \
                patch("utils.template_index.embed_images", side_effect=RuntimeError()):
            self.assertEqual(prepare_index(self.memes, cache=self.cache), (1, False))
        self.assertNotIn("embedding", read_index(self.memes, self.cache)[0])

    def test_changed_source_invalidates_index(self):
        with patch("utils.template_index.urlopen", return_value=self.response()):
            prepare_index(self.memes, use_embeddings=False, cache=self.cache)
        self.memes[0]["image_url"] += "changed"
        self.assertEqual(read_index(self.memes, self.cache), [])

    def test_added_imported_template_reuses_curated_reference_without_writes(self):
        with patch("utils.template_index.urlopen", return_value=self.response()):
            prepare_index(self.memes, use_embeddings=False, cache=self.cache)
        before = {p.name: p.read_bytes() for p in self.cache.iterdir()}
        combined = self.memes + [{"id": "imported", "image_url": "https://example.org/imported.png"}]
        with patch("utils.template_index.urlopen", side_effect=AssertionError("network")) as fetch, \
                patch("utils.template_index.embed_images", side_effect=AssertionError("model")) as embed:
            rows = read_index(combined, self.cache)
        self.assertEqual(rows, [{"id": "a", "hash": image_hash(self.image)}])
        fetch.assert_not_called()
        embed.assert_not_called()
        self.assertEqual({p.name: p.read_bytes() for p in self.cache.iterdir()}, before)

    def test_stale_index_never_reuses_old_id_hash_or_embedding(self):
        with patch("utils.template_index.urlopen", return_value=self.response()):
            prepare_index(self.memes, use_embeddings=False, cache=self.cache)
        path = self.cache / "index.json"
        data = json.loads(path.read_text())
        data["rows"][0].update(hash="1" * 256, embedding=[1.0] * 512)
        path.write_text(json.dumps(data))
        renamed = [{"id": "new-id", "image_url": self.memes[0]["image_url"]}]
        self.assertEqual(read_index(renamed, self.cache), [{"id": "new-id", "hash": image_hash(self.image)}])

    def test_missing_corrupt_blank_and_oversized_cached_images_remain_missing(self):
        with patch("utils.template_index.urlopen", return_value=self.response()):
            prepare_index(self.memes, use_embeddings=False, cache=self.cache)
        extra = [{"id": key, "image_url": f"https://example.org/{key}.png"}
                 for key in ("missing", "corrupt", "blank", "oversized")]
        for meme in extra[1:]:
            path = self.cache / (sha256(meme["image_url"].encode()).hexdigest() + ".png")
            path.write_bytes(b"bad")
            if meme["id"] == "blank":
                Image.new("RGB", (80, 80), "white").save(path, format="PNG")
            if meme["id"] == "oversized":
                path.write_bytes(b"x" * 1025)
        with patch("utils.template_index.MAX_BYTES", 1024):
            rows = read_index(self.memes + extra, self.cache)
        self.assertEqual([row["id"] for row in rows], ["a"])

    def test_reused_references_identify_but_incomplete_analysis_stays_possible(self):
        other_url = "https://example.org/other.png"
        other_path = self.cache / (sha256(other_url.encode()).hexdigest() + ".png")
        other = Image.new("RGB", (80, 80), "black")
        ImageDraw.Draw(other).rectangle((0, 0, 40, 40), fill="white")
        other.save(other_path, format="PNG")
        with patch("utils.template_index.urlopen", return_value=self.response()):
            prepare_index(self.memes, use_embeddings=False, cache=self.cache)
        combined = self.memes + [{"id": "other", "image_url": other_url},
                                 {"id": "missing", "image_url": "https://example.org/missing.png"}]
        rows = read_index(combined, self.cache)
        identity = identify(self.image, rows)
        self.assertEqual(identity.status, "likely")
        self.assertEqual(reliable_template({"identification": identity}, combined), self.memes[0])
        with patch("utils.intelligence.read_index", side_effect=lambda memes: read_index(memes, self.cache)), \
                patch("utils.intelligence.extract_text", return_value=OCRResult("empty")):
            result = analyze(SimpleNamespace(image=self.image), combined)
        self.assertEqual(result["identification"].status, "possible")
        self.assertIsNone(reliable_template(result, combined))
        self.assertTrue(any("2/3" in notice for notice in result["notices"]))

    def test_corrupt_index_is_unavailable(self):
        (self.cache / "index.json").write_text("invalid")
        self.assertEqual(read_index(self.memes, self.cache), [])

    def test_invalid_vector_rejected(self):
        with patch("utils.template_index.urlopen", return_value=self.response()):
            prepare_index(self.memes, use_embeddings=False, cache=self.cache)
        path = self.cache / "index.json"
        data = json.loads(path.read_text())
        data["rows"][0]["embedding"] = [float("nan")] * 512
        path.write_text(json.dumps(data))
        self.assertEqual(read_index(self.memes, self.cache), [])
