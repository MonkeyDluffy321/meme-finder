"""Exercise the real creator UI; inject only uploads and external boundaries."""

from io import BytesIO
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from PIL import Image
import streamlit as st
from streamlit.testing.v1 import AppTest

from utils.auth import ACCOUNT_KEY, clear_private_state
from utils.creator import MAX_CAPTIONS
from utils.rendering import render_draft, RenderingError
from test_library import make_state


APP = Path(__file__).resolve().parents[1] / "app.py"


def upload(color="red", size=(400, 300), fmt="PNG"):
    buffer = BytesIO()
    Image.new("RGB", size, color).save(buffer, format=fmt)
    return buffer


class CreatorAppTests(unittest.TestCase):
    def setUp(self):
        self.files = {}
        self.preview = patch("utils.images.load_preview", return_value=None).start()
        self.uploader = patch("utils.creator_ui.st.file_uploader", side_effect=lambda *a, **kw:
                              self.files.get(kw.get("key"))).start()
        self.download = patch("utils.creator_ui.st.download_button", wraps=st.download_button).start()
        self.render = patch("utils.creator_ui.render_draft", wraps=render_draft).start()
        self.guards = [patch(target, side_effect=AssertionError("Unexpected external side effect")).start()
                       for target in ("utils.intelligence_ui.analyze", "utils.intelligence.explain_upload",
                                      "utils.ocr.extract_text",
                                      "utils.template_index.prepare_index",
                                      "utils.library_ui.record_view", "utils.library_ui.save_meme",
                                      "utils.library_ui.unsave_meme")]
        self.addCleanup(patch.stopall)

    def app(self, with_upload=True):
        if with_upload:
            self.files["creator_upload_0"] = upload()
        app = AppTest.from_file(str(APP))
        app.session_state["creator_active"] = True
        app.run()
        self.assertFalse(app.exception)
        return app

    def key(self, app, field, caption_id=1):
        generation = app.session_state.filtered_state.get("creator_generation", 0)
        return f"creator_caption_{generation}_{caption_id}_{field}"

    def test_creator_navigation_uses_separate_state(self):
        app = AppTest.from_file(str(APP)).run()
        app.button(key="recent").click().run()
        app.button(key="create").click().run()
        self.assertTrue(app.session_state["creator_active"])
        self.assertEqual(app.session_state["library_view"], "recent")
        self.assertEqual(app.title[0].value, "Create a meme")
        self.assertFalse(any("sign in" in item.value for item in app.info))
        self.assertFalse(any(e.label == "Analyze a Meme" for e in app.expander))
        app.button(key="creator_back").click().run()
        self.assertFalse(app.session_state["creator_active"])
        self.assertIn("Recently Viewed", [item.value for item in app.subheader])

    def test_upload_initializes_normalized_draft_and_source_preview(self):
        self.files["creator_upload_0"] = upload(size=(2000, 1000), fmt="JPEG")
        app = self.app(False)
        draft = app.session_state["creator_draft"]
        self.assertEqual((draft.width, draft.height), (1600, 800))
        self.assertEqual(len(draft.captions), 1)
        self.assertEqual(draft.captions[0].text, "")
        self.assertEqual(len(app.get("imgs")) or len(app.get("image")), 2)
        self.assertTrue(any(e.label == "Normalized source image" for e in app.expander))
        self.assertFalse(app.exception)

    def test_no_upload_has_no_preview_or_download(self):
        app = self.app(False)
        self.render.assert_not_called()
        self.download.assert_not_called()
        self.assertNotIn("creator_draft", app.session_state)

    def test_caption_text_changes_preview_and_download_bytes(self):
        app = self.app()
        before = app.session_state["creator_render"].png
        app.text_area(key=self.key(app, "text")).set_value("Hello creator").run()
        self.assertEqual(app.session_state["creator_draft"].captions[0].text, "Hello creator")
        result = app.session_state["creator_render"]
        self.assertNotEqual(result.png, before)
        self.assertEqual(result.png, render_draft(app.session_state["creator_draft"]).png)
        self.assertEqual(self.download.call_args.kwargs["data"], result.png)
        self.assertEqual(self.download.call_args.kwargs["mime"], "image/png")
        with Image.open(BytesIO(result.png)) as image:
            self.assertEqual(image.size, (400, 300))
        self.assertFalse(app.exception)

    def test_every_style_control_updates_model(self):
        app = self.app()
        for field, value in (("x", 25.0), ("y", 40.0), ("width", 65.0),
                             ("font_size", 60), ("outline_width", 5)):
            app.slider(key=self.key(app, field)).set_value(value).run()
        app.selectbox(key=self.key(app, "alignment")).select("right").run()
        app.color_picker(key=self.key(app, "fill_color")).set_value("#ff0000").run()
        app.color_picker(key=self.key(app, "outline_color")).set_value("#0000ff").run()
        caption = app.session_state["creator_draft"].captions[0]
        self.assertEqual((caption.x, caption.y, caption.width), (0.25, 0.4, 0.65))
        self.assertEqual((caption.font_size, caption.outline_width), (60, 5))
        self.assertEqual(caption.alignment, "right")
        self.assertEqual(caption.fill_color.lower(), "#ff0000")
        self.assertEqual(caption.outline_color.lower(), "#0000ff")
        self.assertFalse(app.exception)

    def test_add_remove_preserves_caption_ids_and_text(self):
        app = self.app()
        app.text_area(key=self.key(app, "text")).set_value("First").run()
        app.button(key="creator_add").click().run()
        app.text_area(key=self.key(app, "text", 2)).set_value("Second").run()
        app.button(key=self.key(app, "remove", 1)).click().run()
        app.button(key="creator_add").click().run()
        self.assertEqual([c.id for c in app.session_state["creator_draft"].captions], [2, 3])
        self.assertEqual(app.text_area(key=self.key(app, "text", 2)).value, "Second")
        self.assertEqual(app.text_area(key=self.key(app, "text", 3)).value, "")
        self.assertFalse(app.exception)

    def test_caption_limit_disables_add(self):
        app = self.app()
        for _ in range(MAX_CAPTIONS - 1):
            app.button(key="creator_add").click().run()
        self.assertTrue(app.button(key="creator_add").disabled)
        app.button(key=self.key(app, "remove", 1)).click().run()
        self.assertFalse(app.button(key="creator_add").disabled)

    def test_remove_all_keeps_image_downloadable(self):
        app = self.app()
        app.button(key=self.key(app, "remove")).click().run()
        self.assertEqual(app.session_state["creator_draft"].captions, ())
        self.assertEqual(self.download.call_args.kwargs["data"], app.session_state["creator_render"].png)
        self.assertFalse(app.exception)

    def test_unchanged_rerun_reuses_only_session_render(self):
        app = self.app()
        first = app.session_state["creator_render"]
        app.run()
        self.render.assert_called_once()
        self.assertEqual(app.session_state["creator_render"], first)

    def test_overflow_names_caption_and_keeps_font_size(self):
        app = self.app()
        app.text_area(key=self.key(app, "text")).set_value("Clipped\ncaption").run()
        app.slider(key=self.key(app, "y")).set_value(99.0).run()
        self.assertTrue(any("Clipped text: Caption 1" in warning.value for warning in app.warning))
        self.assertEqual(app.session_state["creator_draft"].captions[0].font_size, 40)

    def test_clear_rotates_widgets_and_removes_outputs(self):
        app = self.app()
        app.text_area(key=self.key(app, "text")).set_value("Private caption").run()
        app.button(key="creator_clear").click().run()
        self.assertEqual(app.session_state["creator_generation"], 1)
        self.assertNotIn("creator_draft", app.session_state)
        self.assertNotIn("creator_render", app.session_state)
        self.assertNotIn("creator_render_key", app.session_state)
        self.assertFalse(app.get("download_button"))
        self.assertFalse(any(key.startswith("creator_caption_") for key in app.session_state.filtered_state))
        self.assertEqual(self.uploader.call_args.kwargs["key"], "creator_upload_1")
        self.files["creator_upload_1"] = upload()
        app.run()
        self.assertEqual(app.text_area(key=self.key(app, "text")).value, "")

    def test_explicit_upload_removal_clears_but_hidden_uploader_does_not(self):
        app = self.app()
        self.files.clear()
        app.run()
        self.assertIn("creator_draft", app.session_state)
        # AppTest cannot set the file uploader; inject its removal callback signal.
        app.session_state["creator_upload_changed"] = True
        app.run()
        self.assertNotIn("creator_draft", app.session_state)
        self.assertNotIn("creator_render", app.session_state)
        self.assertFalse(app.exception)

    def test_replacement_resets_captions_and_exports(self):
        app = self.app()
        app.text_area(key=self.key(app, "text")).set_value("Old text").run()
        previous = app.session_state["creator_render"].png
        self.files["creator_upload_0"] = upload("blue", (200, 100))
        app.run()
        self.assertEqual(app.text_area(key=self.key(app, "text")).value, "")
        self.assertEqual(app.session_state["creator_render"].width, 200)
        self.assertNotEqual(app.session_state["creator_render"].png, previous)
        self.assertFalse(app.exception)

    def test_invalid_upload_discards_former_preview_and_keeps_error_on_rerun(self):
        app = self.app()
        self.files["creator_upload_0"] = BytesIO(b"invalid")
        app.run()
        self.assertTrue(app.error)
        self.assertNotIn("creator_draft", app.session_state)
        self.assertNotIn("creator_render", app.session_state)
        self.assertFalse(app.get("download_button"))
        app.run()
        self.assertTrue(app.error)

    def test_render_failure_cannot_offer_stale_download(self):
        app = self.app()
        self.download.reset_mock()
        self.render.side_effect = RenderingError("Rendering unavailable")
        app.text_area(key=self.key(app, "text")).set_value("New text").run()
        self.assertTrue(app.error)
        self.assertNotIn("creator_render", app.session_state)
        self.assertNotIn("creator_render_key", app.session_state)
        self.download.assert_not_called()
        self.assertFalse(app.get("download_button"))
        self.render.side_effect = None
        app.run()
        self.assertIn("creator_render", app.session_state)
        self.assertFalse(app.exception)

    def test_invalid_caption_blocks_download_until_corrected(self):
        app = self.app()
        app.text_area(key=self.key(app, "text")).set_value("Invalid\x00text").run()
        self.assertTrue(app.error)
        self.assertNotIn("creator_render", app.session_state)
        self.assertFalse(app.get("download_button"))
        app.text_area(key=self.key(app, "text")).set_value("Fixed").run()
        self.assertFalse(app.error)
        self.assertIn("creator_render", app.session_state)

    def test_draft_survives_leaving_and_reentering_creator(self):
        app = self.app()
        app.text_area(key=self.key(app, "text")).set_value("Keep me").run()
        app.slider(key=self.key(app, "x")).set_value(35.0).run()
        self.files.clear()  # A real hidden uploader may be removed by Streamlit.
        app.button(key="saved").click().run()
        app.button(key="create").click().run()
        self.assertEqual(app.text_area(key=self.key(app, "text")).value, "Keep me")
        self.assertEqual(app.slider(key=self.key(app, "x")).value, 35.0)
        self.assertFalse(app.exception)

    def test_search_filters_and_page_survive_back_button(self):
        app = AppTest.from_file(str(APP)).run()
        app.button(key="next").click().run()
        app.button(key="create").click().run()
        app.run()
        app.button(key="creator_back").click().run()
        self.assertEqual(app.session_state["page"], 1)
        app.text_input(key="query").set_value("work").run()
        app.multiselect(key="categories").select("work").run()
        app.button(key="create").click().run()
        app.run()
        app.button(key="creator_back").click().run()
        self.assertEqual(app.text_input(key="query").value, "work")
        self.assertEqual(app.multiselect(key="categories").value, ["work"])
        self.assertFalse(app.exception)

    def test_existing_routes_exit_creator_and_home_still_resets(self):
        app = self.app(False)
        for key, heading in (("saved", "Saved Memes"), ("recent", "Recently Viewed"), ("home", "Browse Memes")):
            app.button(key=key).click().run()
            self.assertFalse(app.session_state["creator_active"])
            self.assertIn(heading, [s.value for s in app.subheader])
            app.button(key="create").click().run()
        app.button(key="home").click().run()
        self.assertEqual(app.session_state["query"], "")
        self.assertEqual(app.session_state["page"], 0)
        self.assertTrue(any(e.label == "Analyze a Meme" for e in app.expander))

    def test_signed_in_creator_makes_no_discovery_ai_or_database_calls(self):
        state, client, query = make_state()
        self.files["creator_upload_0"] = upload()
        app = AppTest.from_file(str(APP))
        app.session_state[ACCOUNT_KEY] = state[ACCOUNT_KEY]
        app.session_state["creator_active"] = True
        with patch("utils.search.search_memes") as search, patch("utils.library.fetch_library") as library:
            app.run()
            app.text_area(key=self.key(app, "text")).set_value("Local only").run()
            app.button(key="creator_add").click().run()
            app.run()
            search.assert_not_called()
            library.assert_not_called()
        client.table.assert_not_called()
        client.auth.get_session.assert_not_called()
        self.preview.assert_not_called()
        for guard in self.guards:
            guard.assert_not_called()
        self.assertFalse(app.exception)

    def test_private_state_cleanup_discards_creator_and_rotates_generation(self):
        app = self.app()
        state = dict(app.session_state.filtered_state)
        state["query"] = "keep discovery"
        clear_private_state(state)
        self.assertEqual(state["creator_generation"], 1)
        self.assertEqual(state["query"], "keep discovery")
        self.assertEqual([key for key in state if key.startswith("creator_")], ["creator_generation"])


if __name__ == "__main__":
    unittest.main()
