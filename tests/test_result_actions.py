from io import BytesIO
from pathlib import Path
import unittest
from unittest.mock import patch

from PIL import Image
import streamlit as st
from streamlit.testing.v1 import AppTest

from utils.creator import CreatorDraft


APP = Path(__file__).resolve().parents[1] / "app.py"


def picture(color):
    output = BytesIO()
    Image.new("RGB", (80, 60), color).save(output, format="PNG")
    return output.getvalue()


class ResultActionTests(unittest.TestCase):
    def setUp(self):
        self.red, self.blue = picture("red"), picture("blue")
        self.templates = [dict(id="one", name="First", meaning="First template", image_url="unused"),
                          dict(id="two", name="Second", meaning="Second template", image_url="unused")]
        self.finished = dict(instance_key="finished", caption_text="A caption", provider="fixture",
                             image_url="https://example.org/image.png")
        for target, kwargs in [
            ("utils.search_all.search_all", dict(return_value={"memes": [self.finished], "templates": self.templates})),
            ("utils.images.load_preview", dict(return_value=self.blue)),
            ("utils.images.load_external_preview", dict(return_value=self.red)),
        ]:
            mock = patch(target, **kwargs)
            mock.start()
            self.addCleanup(mock.stop)

    def app(self):
        app = AppTest.from_file(str(APP), default_timeout=20).run()
        self.assertFalse(app.exception)
        return app

    def test_downloads_use_exact_displayed_bytes(self):
        with patch("utils.result_actions.st.download_button", wraps=st.download_button) as download:
            self.app()
        calls = {call.kwargs["key"]: call for call in download.call_args_list}
        for key, content in (("finished-finished", self.red), ("template-one", self.blue), ("template-two", self.blue)):
            call = calls["download-" + key]
            self.assertEqual(call.args[0], "Download")
            self.assertEqual(call.kwargs["data"], content)
            self.assertEqual(call.kwargs["mime"], "image/png")

    def test_selected_template_replaces_draft_and_survives_navigation(self):
        app = self.app()
        app.session_state["creator_draft"] = CreatorDraft.from_bytes(self.red)
        app.session_state["creator_render"] = "stale"
        app.button(key="create-template-two").click().run()
        self.assertFalse(app.exception)
        self.assertTrue(app.session_state["creator_active"])
        self.assertEqual(app.session_state["creator_template"], {"id": "two", "name": "Second"})
        self.assertEqual(app.session_state["creator_draft"].base_png, CreatorDraft.from_bytes(self.blue).base_png)
        self.assertTrue(any(t.value == "Selected template: Second" for t in app.text))
        app.button(key="creator_back").click().run()
        app.button(key="create").click().run()
        self.assertEqual(app.session_state["creator_template"]["id"], "two")
        self.assertFalse(app.exception)

    def test_unavailable_corrupt_and_failed_images_keep_results(self):
        for options in (dict(return_value=None), dict(return_value=b"bad"), dict(side_effect=RuntimeError("offline"))):
            with self.subTest(options=options), patch("utils.images.load_preview", **options), patch("utils.images.load_external_preview", **options):
                app = self.app()
                for key in ("download-finished-finished", "download-template-one", "create-template-one"):
                    self.assertTrue(app.button(key=key).disabled)
                self.assertTrue(any(t.value == "A caption" for t in app.text))
                self.assertIn("Second", [h.value for h in app.subheader])
                self.assertFalse(app.button(key="save-one").disabled)

    def test_preparation_failure_isolated_from_other_results(self):
        with patch("utils.images.load_preview", side_effect=[b"bad", self.blue]):
            app = self.app()
        self.assertTrue(app.button(key="download-template-one").disabled)
        self.assertFalse(app.button(key="create-template-two").disabled)
        self.assertEqual(len(app.get("download_button")), 2)

    def test_save_callback_unchanged(self):
        with patch("utils.library_ui.save_meme") as save:
            app = self.app()
            app.button(key="save-two").click().run()
        self.assertFalse(app.exception)
        self.assertEqual(save.call_args.args[1], "two")
        self.assertFalse(app.session_state.filtered_state.get("creator_active", False))

    def test_creator_validation_failure_keeps_existing_draft(self):
        app = self.app()
        old = CreatorDraft.from_bytes(self.red)
        app.session_state["creator_draft"] = old
        with patch("utils.creator_ui.CreatorDraft.from_bytes", side_effect=ValueError("bad")):
            app.button(key="create-template-two").click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state["creator_draft"], old)
        self.assertTrue(any("Template image unavailable" in i.value for i in app.info))
