from types import SimpleNamespace
import unittest
from unittest.mock import Mock


from utils.intelligence import explain_upload
from utils.identification import Identification
from utils.ocr import OCRResult
from utils.vision import Explanation, VisionResult



def success():
    return VisionResult("ok", Explanation("Visible scene.", "An arbitrary meme explanation.",
                        "An unexpected contrast.", ["A supported phrase."], "Intent is uncertain."))


class VisionOrchestrationTests(unittest.TestCase):
    def setUp(self):
        self.upload = SimpleNamespace(preview=b"normalized")
        self.local = {"ocr": OCRResult("ok", "raw"), "identification": Identification("unknown")}
        self.provider = Mock()
        self.provider.explain.return_value = success()
        self.memes = [{"id": "a", "name": "A", "meaning": "Meaning", "description": "Scene", "situations": ["Use"]}]

    def test_unknown_meme_still_explained(self):
        self.assertEqual(explain_upload(self.upload, self.local, self.memes, provider=self.provider).status, "ok")
        self.provider.explain.assert_called_once_with(b"normalized", "raw", None, None)

    def test_ocr_failure_does_not_block_visual_explanation(self):
        self.local["ocr"] = OCRResult("failed")
        explain_upload(self.upload, self.local, [], provider=self.provider)
        self.provider.explain.assert_called_once_with(b"normalized", "", None, None)

    def test_correction_passed_even_if_intentionally_empty(self):
        for text in ("corrected", ""):
            explain_upload(self.upload, self.local, [], text, self.provider)
            self.assertEqual(self.provider.explain.call_args.args[2], text)

    def test_weak_hint_excluded_strong_hint_grounded(self):
        for status in ("possible", "likely"):
            self.local["identification"] = Identification(status, [{"id": "a"}])
            explain_upload(self.upload, self.local, self.memes, provider=self.provider)
            hint = self.provider.explain.call_args.args[3]
            if status == "possible":
                self.assertIsNone(hint)
            else:
                self.assertEqual(hint["meaning"], "Meaning")
                self.assertNotIn("id", hint)

    def test_replaceable_provider_failure(self):
        self.provider.explain.side_effect = RuntimeError("private")
        result = explain_upload(self.upload, self.local, [], provider=self.provider)
        self.assertEqual(result.status, "error")
        self.assertNotIn("private", result.message)


    def test_default_explainer_is_unavailable_without_accessing_inputs(self):
        result = explain_upload(None, None, None)
        self.assertEqual(result.status, "unavailable")
        self.assertIsNone(result.explanation)
