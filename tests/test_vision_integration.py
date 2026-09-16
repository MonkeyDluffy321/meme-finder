from io import BytesIO
import base64
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from PIL import Image
from streamlit.testing.v1 import AppTest

from utils.intelligence import explain_upload
from utils.identification import Identification
from utils.ocr import OCRResult
from utils.vision import Explanation, VisionResult

APP = Path(__file__).resolve().parents[1] / "app.py"


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


class VisionAppTests(unittest.TestCase):
    def setUp(self):
        patch("utils.images.load_preview", return_value=None).start()
        self.local = {"ocr": OCRResult("failed"), "identification": Identification("unknown"), "notices": []}
        patch("utils.intelligence_ui.analyze", return_value=self.local).start()
        self.cloud = patch("utils.intelligence_ui.explain_upload", return_value=success()).start()
        self.buffer = BytesIO()
        Image.new("RGB", (30, 30), "red").save(self.buffer, format="PNG")
        self.uploader = patch("utils.intelligence_ui.st.file_uploader", return_value=self.buffer).start()
        self.addCleanup(patch.stopall)

    def test_explicit_click_once_unknown_renders_and_no_database_write(self):
        with patch("utils.library.record_view") as history, patch("utils.library.save_meme") as save:
            app = AppTest.from_file(str(APP)).run()
            app.run()
            self.cloud.assert_not_called()
            self.assertTrue(any("sends the normalized image" in i.value for i in app.info))
            app.button(key="v3_analyze").click().run()
            self.cloud.assert_not_called()
            app.text_area(key="v3_text").set_value("correct caption").run()
            app.button(key="v3_explain").click().run()
            self.assertFalse(app.exception)
            self.cloud.assert_called_once()
            self.assertEqual(self.cloud.call_args.args[3], "correct caption")
            self.assertTrue(any("arbitrary meme explanation" in t.value for t in app.text))
            app.run()
            self.cloud.assert_called_once()
            history.assert_not_called()
            save.assert_not_called()

    def test_cloud_without_ocr_is_available(self):
        app = AppTest.from_file(str(APP)).run()
        app.button(key="v3_explain").click().run()
        self.assertFalse(app.exception)
        self.cloud.assert_called_once()

    def test_corrected_sentinel_reaches_gemini_only_on_explicit_click(self):
        # Exercise the real UI -> orchestration -> provider path; mock only SDK I/O.
        self.cloud.side_effect = explain_upload
        self.local["ocr"] = OCRResult("ok", "fuck around / find out")
        with patch("utils.vision.read_api_key", return_value="mock-key"), \
                patch("google.genai.Client") as factory, \
                patch("utils.library.record_view") as history, \
                patch("utils.library.save_meme") as save:
            client = factory.return_value.__enter__.return_value
            request = client.interactions.create
            request.return_value = SimpleNamespace(
                status="completed", output_text=json.dumps(vars(success().explanation)))
            app = AppTest.from_file(str(APP)).run()
            app.button(key="v3_analyze").click().run()
            self.assertEqual(app.text_area(key="v3_text").value, "fuck around / find out")
            app.text_area(key="v3_text").set_value("BLUE UMBRELLA TEST").run()
            app.run()
            factory.assert_not_called()
            app.button(key="v3_explain").click().run()
            self.assertFalse(app.exception)
            request.assert_called_once()
            args = request.call_args.kwargs
            evidence = json.loads(args["input"][1]["text"])
            self.assertEqual(evidence["User-corrected visible text"], "BLUE UMBRELLA TEST")
            self.assertEqual(evidence["ocr_text"], "fuck around / find out")
            self.assertEqual(base64.b64decode(args["input"][0]["data"]),
                             app.session_state["v3_validated"].preview)
            self.assertFalse(args["store"])
            app.run()
            request.assert_called_once()
            history.assert_not_called()
            save.assert_not_called()

    def test_fallback_without_template_keeps_text_and_suggestions(self):
        self.cloud.return_value = VisionResult("unavailable", message="Cloud explanation unavailable")
        app = AppTest.from_file(str(APP)).run()
        app.text_area(key="v3_text").set_value("2 choices").run()
        app.button(key="v3_explain").click().run()
        self.assertFalse(app.exception)
        self.assertTrue(any("Limited explanation available" in m.value for m in app.markdown))
        self.assertEqual(app.text_area(key="v3_text").value, "2 choices")
        app.button(key="v3_find_related").click().run()
        self.assertTrue(app.session_state["v3_related"])
        self.cloud.assert_called_once()

    def test_fallback_only_uses_reliable_template(self):
        self.cloud.return_value = VisionResult("error")
        self.local["identification"] = Identification("likely", [{"id": "drake-hotline-bling"}])
        app = AppTest.from_file(str(APP)).run()
        app.button(key="v3_analyze").click().run()
        app.button(key="v3_explain").click().run()
        self.assertFalse(app.exception)
        self.assertTrue(any("General collection metadata" in c.value for c in app.caption))

    def test_edit_replacement_and_clear_invalidate_explanation(self):
        app = AppTest.from_file(str(APP)).run()
        app.button(key="v3_explain").click().run()
        app.text_area(key="v3_text").set_value("new text").run()
        self.assertNotIn("v3_explanation", app.session_state)
        self.cloud.assert_called_once()
        app.button(key="v3_explain").click().run()
        replacement = BytesIO()
        Image.new("RGB", (30, 30), "blue").save(replacement, format="PNG")
        self.uploader.return_value = replacement
        app.run()
        self.assertNotIn("v3_explanation", app.session_state)
        self.assertEqual(self.cloud.call_count, 2)
        app.button(key="v3_explain").click().run()
        self.uploader.return_value = None
        app.button(key="v3_clear").click().run()
        self.assertFalse(app.exception)
        self.assertNotIn("v3_explanation", app.session_state)

    def test_removing_upload_clears_explanation(self):
        app = AppTest.from_file(str(APP)).run()
        app.button(key="v3_explain").click().run()
        self.uploader.return_value = None
        app.run()
        self.assertNotIn("v3_explanation", app.session_state)
