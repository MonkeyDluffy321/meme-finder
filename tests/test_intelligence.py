from types import SimpleNamespace
import unittest
from unittest.mock import patch
from PIL import Image

from utils.intelligence import analyze
from utils.ocr import OCRResult
from utils.identification import Identification


class IntelligenceTests(unittest.TestCase):
    def setUp(self):
        self.upload = SimpleNamespace(image=Image.new("RGB", (20, 20)))
        self.memes = [{"id": "a"}, {"id": "b"}]
        self.ocr = patch("utils.intelligence.extract_text", return_value=OCRResult("ok", "caption")).start()
        self.index = patch("utils.intelligence.read_index", return_value=[]).start()
        self.addCleanup(patch.stopall)

    def test_no_index_preserves_ocr(self):
        result = analyze(self.upload, self.memes)
        self.assertEqual(result["ocr"].text, "caption")
        self.assertEqual(result["identification"].status, "unavailable")

    def test_ocr_failure_preserves_identification(self):
        self.ocr.side_effect = RuntimeError()
        with patch("utils.intelligence.identify", return_value=Identification("unknown")):
            result = analyze(self.upload, self.memes)
        self.assertEqual(result["ocr"].status, "failed")
        self.assertEqual(result["identification"].status, "unknown")

    def test_model_failure_falls_back(self):
        self.index.return_value = [{"id": "a", "hash": "0" * 256, "embedding": [1]}]
        with patch("utils.intelligence.embed_images", side_effect=RuntimeError()), \
                patch("utils.intelligence.identify", return_value=Identification("likely")) as identify:
            result = analyze(self.upload, self.memes)
        self.assertIsNone(identify.call_args.args[2])
        self.assertEqual(result["identification"].status, "possible")
        self.assertTrue(any("hash-only" in n for n in result["notices"]))

    def test_index_failure_preserves_text(self):
        self.index.side_effect = OSError()
        self.assertEqual(analyze(self.upload, self.memes)["ocr"].text, "caption")
