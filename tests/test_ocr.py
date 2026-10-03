from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from PIL import Image

from utils.ocr import extract_text, select_caption
from utils import ocr


class OCRTests(unittest.TestCase):
    def test_caption_selection_excludes_only_isolated_numeric_lines(self):
        cases = (
            ("38\nME PLANTING SEEDS OF DOUBT\n50", "ME PLANTING SEEDS OF DOUBT"),
            (" 38 \nME PLANTING SEEDS OF DOUBT\n50", "ME PLANTING SEEDS OF DOUBT"),
            ("2006 Honda Civic\nTop 10 anime\nWindows 11", "2006 Honda Civic\nTop 10 anime\nWindows 11"),
            ("Me: I need sleep\nAlso me: one more episode", "Me: I need sleep\nAlso me: one more episode"),
            ("", ""),
            ("38\n50", ""),
            ("Windows\n11 reasons to upgrade", "Windows\n11 reasons to upgrade"),
        )
        for raw, expected in cases:
            with self.subTest(raw=raw):
                self.assertEqual(select_caption(raw), expected)

    def test_missing_engine(self):
        with patch("utils.ocr.get_engine", side_effect=ImportError()):
            self.assertEqual(extract_text(Image.new("RGB", (10, 10))).status, "unavailable")

    def test_inference_failure(self):
        with patch("utils.ocr.get_engine", return_value=Mock(side_effect=RuntimeError())):
            self.assertEqual(extract_text(Image.new("RGB", (10, 10))).status, "failed")

    def test_empty_and_readable_outputs(self):
        for texts, scores, expected in [(None, None, "empty"), ([], [], "empty"),
                                        (["hello", "world"], [0.9, 0.95], "ok"),
                                        (["maybe"], [0.4], "uncertain")]:
            engine = Mock(return_value=SimpleNamespace(txts=texts, scores=scores))
            with patch("utils.ocr.get_engine", return_value=engine):
                result = extract_text(Image.new("RGB", (10, 10)))
                self.assertEqual(result.status, expected)
                if expected == "ok":
                    self.assertEqual(result.text, "hello\nworld")

    def test_rgb_converted_to_bgr(self):
        engine = Mock(return_value=SimpleNamespace(txts=None))
        with patch("utils.ocr.get_engine", return_value=engine):
            extract_text(Image.new("RGB", (10, 10), "red"))
        self.assertEqual(engine.call_args.args[0][0, 0].tolist(), [0, 0, 255])

    def test_successful_engine_reused_but_failure_retryable(self):
        factory = Mock(side_effect=[RuntimeError(), object()])
        with patch.object(ocr, "_ENGINE", None), \
                patch.dict("sys.modules", {"rapidocr": SimpleNamespace(RapidOCR=factory)}):
            self.assertEqual(extract_text(Image.new("RGB", (10, 10))).status, "unavailable")
            first = ocr.get_engine()
            self.assertIs(first, ocr.get_engine())
        self.assertEqual(factory.call_count, 2)
