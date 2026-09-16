import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch, MagicMock
from io import BytesIO
from PIL import Image, ImageDraw

from utils.template_index import prepare_index, read_index, image_hash, informative


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
