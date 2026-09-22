from io import BytesIO
from pathlib import Path
import unittest
from unittest.mock import patch
from PIL import Image
from streamlit.testing.v1 import AppTest

from utils.ocr import OCRResult
from utils.identification import Identification
from utils.auth import clear_private_state

APP = Path(__file__).resolve().parents[1] / "app.py"


class IntelligenceAppTests(unittest.TestCase):
    def setUp(self):
        patch("utils.images.load_preview", return_value=None).start()
        self.prepare = patch("utils.template_index.prepare_index").start()
        self.analyze = patch("utils.intelligence_ui.analyze", return_value={
            "ocr": OCRResult("empty"), "identification": Identification("unknown"), "notices": []}).start()
        self.addCleanup(patch.stopall)

    def test_idle_home_is_lazy_and_saved_hides_upload(self):
        app = AppTest.from_file(str(APP)).run()
        self.assertFalse(app.exception)
        self.assertTrue(any(e.label == "Analyze a Meme" for e in app.expander))
        self.prepare.assert_not_called()
        self.analyze.assert_not_called()
        app.button(key="saved").click().run()
        self.assertFalse(any(e.label == "Analyze a Meme" for e in app.expander))

    def test_upload_analyze_edit_clear_and_no_database_writes(self):
        buffer = BytesIO()
        Image.new("RGB", (30, 30), "red").save(buffer, format="PNG")
        # AppTest has no uploader setter; inject only that boundary and exercise
        # the real validation, rendering, buttons and session state.
        with patch("utils.intelligence_ui.st.file_uploader", return_value=buffer), \
                patch("utils.library.record_view") as history, \
                patch("utils.library.save_meme") as save:
            app = AppTest.from_file(str(APP)).run()
            self.assertFalse(app.exception)
            self.assertIn("v3_validated", app.session_state)
            self.assertTrue(any(button.key == "v3_explain" for button in app.button))
            app.button(key="v3_analyze").click().run()
            self.assertFalse(app.exception)
            self.assertTrue(any("No reliable match" in m.value for m in app.caption))
            app.text_area(key="v3_text").set_value("2 choices").run()
            app.button(key="v3_find_related").click().run()
            self.assertFalse(app.exception)
            self.assertTrue(app.session_state["v3_related"])
            app.text_area(key="v3_text").set_value("different caption").run()
            self.assertNotIn("v3_related", app.session_state)
            self.analyze.assert_called_once()
            history.assert_not_called()
            save.assert_not_called()
        app.button(key="v3_clear").click().run()
        self.assertFalse(app.exception)
        self.assertNotIn("v3_result", app.session_state)

    def test_invalid_upload_does_not_analyze(self):
        with patch("utils.intelligence_ui.st.file_uploader", return_value=BytesIO(b"bad")):
            app = AppTest.from_file(str(APP)).run()
            self.assertFalse(app.exception)
            self.assertTrue(app.error)
            self.analyze.assert_not_called()

    def test_local_explanation_questions_edits_replacement_and_clear(self):
        self.analyze.return_value["identification"] = Identification(
            "likely", [{"id": "drake-hotline-bling"}])
        self.analyze.return_value["ocr"] = OCRResult("ok", "raw caption")
        buffer = BytesIO()
        Image.new("RGB", (30, 30), "red").save(buffer, format="PNG")
        with patch("utils.intelligence_ui.st.file_uploader", return_value=buffer) as uploader, \
                patch("utils.library.record_view") as history, patch("utils.library.save_meme") as save:
            app = AppTest.from_file(str(APP)).run()
            self.assertNotIn("v3_explanation", app.session_state)
            app.button(key="v3_analyze").click().run()
            app.text_area(key="v3_text").set_value("corrected caption").run()
            app.text_input(key="v3_question").set_value("When should I use this meme?").run()
            app.button(key="v3_explain").click().run()
            self.assertFalse(app.exception)
            explanation = app.session_state["v3_explanation"].explanation
            self.assertEqual(explanation.intent, "usage")
            self.assertEqual(explanation.visible_text, "corrected caption")
            self.assertTrue(any("Template: Drake" in t.value for t in app.text))
            app.text_input(key="v3_question").set_value("Show similar memes").run()
            self.assertNotIn("v3_explanation", app.session_state)
            app.button(key="v3_explain").click().run()
            self.assertEqual(app.session_state["v3_explanation"].explanation.intent, "similar")
            app.text_area(key="v3_text").set_value("").run()
            self.assertNotIn("v3_explanation", app.session_state)
            app.button(key="v3_explain").click().run()
            self.assertEqual(app.session_state["v3_explanation"].explanation.visible_text, "")
            replacement = BytesIO()
            Image.new("RGB", (30, 30), "blue").save(replacement, format="PNG")
            uploader.return_value = replacement
            app.run()
            self.assertNotIn("v3_explanation", app.session_state)
            app.button(key="v3_explain").click().run()
            self.assertEqual(app.session_state["v3_explanation"].status, "abstained")
            app.text_area(key="v3_text").set_value("Expectation: rest\nReality: answering work emails").run()
            app.button(key="v3_explain").click().run()
            self.assertFalse(app.exception)
            self.assertEqual(app.session_state["v3_explanation"].status, "ok")
            self.assertTrue(any("hoped-for outcome" in t.value for t in app.text))
            uploader.return_value = None
            app.button(key="v3_clear").click().run()
            self.assertFalse(app.exception)
            self.assertNotIn("v3_explanation", app.session_state)
            history.assert_not_called()
            save.assert_not_called()

    def test_logout_clears_upload_state(self):
        state = {"v3_result": object(), "v3_upload_0": object(), "query": "cat"}
        clear_private_state(state)
        self.assertEqual(state, {"query": "cat", "v3_generation": 1})

    def test_replacement_discards_previous_analysis(self):
        buffer = BytesIO()
        Image.new("RGB", (30, 30), "red").save(buffer, format="PNG")
        with patch("utils.intelligence_ui.st.file_uploader", return_value=buffer) as uploader:
            app = AppTest.from_file(str(APP)).run()
            app.button(key="v3_analyze").click().run()
            self.assertIn("v3_result", app.session_state)
            replacement = BytesIO()
            Image.new("RGB", (30, 30), "blue").save(replacement, format="PNG")
            uploader.return_value = replacement
            app.run()
            self.assertFalse(app.exception)
            self.assertNotIn("v3_result", app.session_state)

    def test_reliable_match_displays_local_metadata(self):
        self.analyze.return_value["identification"] = Identification(
            "likely", [{"id": "drake-hotline-bling"}])
        buffer = BytesIO()
        Image.new("RGB", (30, 30), "red").save(buffer, format="PNG")
        with patch("utils.intelligence_ui.st.file_uploader", return_value=buffer):
            app = AppTest.from_file(str(APP)).run()
            app.button(key="v3_analyze").click().run()
            self.assertFalse(app.exception)
            self.assertTrue(any("Drake" in m.value for m in app.markdown))

    def test_possible_match_remains_uncertain(self):
        self.analyze.return_value["identification"] = Identification(
            "possible", [{"id": "drake-hotline-bling"}])
        self.analyze.return_value["ocr"] = OCRResult("unavailable")
        buffer = BytesIO()
        Image.new("RGB", (30, 30), "red").save(buffer, format="PNG")
        with patch("utils.intelligence_ui.st.file_uploader", return_value=buffer):
            app = AppTest.from_file(str(APP)).run()
            app.button(key="v3_analyze").click().run()
            self.assertFalse(app.exception)
            self.assertTrue(any("Possible match" in m.value for m in app.caption))
            self.assertTrue(any("Too uncertain" in m.value for m in app.caption))
            self.assertTrue(any("OCR unavailable" in c.value for c in app.caption))
