from io import BytesIO
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

import test_creator_app as creator_tests
from utils.auth import clear_private_state, ACCOUNT_KEY, logout, current_account
from utils.rendering import render_draft, RenderingError
from test_library import make_state


class ImageLayerAppTests(unittest.TestCase):
    setUp = creator_tests.CreatorAppTests.setUp
    app = creator_tests.CreatorAppTests.app

    def key(self, app, field, layer_id=1):
        state = app.session_state.filtered_state
        return f"creator_image_{state.get('creator_generation', 0)}_{state.get('creator_image_epoch', 0)}_{layer_id}_{field}"

    def add(self, app, color="blue"):
        layer_id = app.session_state["creator_draft"].next_image_id
        app.button(key="creator_add_image").click().run()
        self.files[self.key(app, "upload", layer_id)] = creator_tests.upload(color)
        app.run()
        self.assertFalse(app.exception)
        return layer_id

    def test_add_image_and_exact_png_export(self):
        app = self.app()
        old = app.session_state["creator_render"].png
        self.add(app)
        draft = app.session_state["creator_draft"]
        self.assertEqual(len(draft.image_layers), 1)
        result = app.session_state["creator_render"]
        self.assertNotEqual(result.png, old)
        self.assertEqual(result.png, render_draft(draft).png)
        self.assertEqual(self.download.call_args.kwargs["data"], result.png)
        self.assertTrue(any(c.value == "1 / 8 image layers" for c in app.caption))

    def test_edit_every_image_control(self):
        app = self.app()
        self.add(app)
        previous_key = app.session_state["creator_render_key"]
        for field, value in (("x", -20.0), ("y", 30.0), ("width", 50.0), ("height", 60.0),
                             ("rotation", 45.0), ("opacity", 50)):
            app.slider(key=self.key(app, field)).set_value(value).run()
        app.selectbox(key=self.key(app, "fit")).select("cover").run()
        layer = app.session_state["creator_draft"].image_layers[0]
        self.assertEqual((layer.x, layer.y, layer.width, layer.height), (-0.2, 0.3, 0.5, 0.6))
        self.assertEqual((layer.rotation, layer.opacity, layer.fit), (45, 50, "cover"))
        self.assertNotEqual(app.session_state["creator_render_key"], previous_key)
        self.assertFalse(app.exception)

    def test_slider_to_number_sync_all_fields(self):
        app = self.app()
        self.add(app)
        for field, value in (("x", 37.0), ("y", -29.0), ("width", 64.0),
                             ("height", 51.0), ("rotation", -43.0), ("opacity", 72)):
            with self.subTest(field=field):
                app.slider(key=self.key(app, field)).set_value(value).run()
                self.assertEqual(app.number_input(key=self.key(app, field + "_number")).value, value)
                self.assertFalse(app.exception)

    def test_number_to_slider_sync_all_fields_and_model_units(self):
        app = self.app()
        self.add(app)
        for field, value in (("x", -29.0), ("y", -37.0), ("width", 41.0),
                             ("height", 62.0), ("rotation", 123.0), ("opacity", 23)):
            with self.subTest(field=field):
                app.number_input(key=self.key(app, field + "_number")).set_value(value).run()
                self.assertEqual(app.slider(key=self.key(app, field)).value, value)
                model_value = getattr(app.session_state["creator_draft"].image_layers[0], field)
                self.assertEqual(model_value, value / 100 if field in ("x", "y", "width", "height") else value)
                self.assertFalse(app.exception)
        self.assertIs(type(app.session_state["creator_draft"].image_layers[0].opacity), int)

    def test_paired_controls_preserve_ranges_and_accept_boundaries(self):
        app = self.app()
        self.add(app)
        for field, low, high in (("x", -100.0, 100.0), ("y", -100.0, 100.0),
                                 ("width", 1.0, 100.0), ("height", 1.0, 100.0),
                                 ("rotation", -180.0, 180.0), ("opacity", 0, 100)):
            with self.subTest(field=field):
                for widget in (app.slider(key=self.key(app, field)),
                               app.number_input(key=self.key(app, field + "_number"))):
                    self.assertEqual((widget.proto.min, widget.proto.max), (low, high))
                    self.assertEqual(widget.proto.step, 1)
                for value in (low, high):
                    app.number_input(key=self.key(app, field + "_number")).set_value(value).run()
                    self.assertEqual(app.slider(key=self.key(app, field)).value, value)
                    self.assertFalse(app.exception)

    def test_numeric_changes_are_isolated_and_equivalent_pixels_match(self):
        app = self.app()
        self.add(app)
        self.add(app, "green")
        first = app.session_state["creator_draft"].image_layers[0]
        second = app.session_state["creator_draft"].image_layers[1]
        for field, value in (("x", 37.0), ("y", 23.0), ("width", 55.0),
                             ("height", 45.0), ("rotation", 30.0), ("opacity", 65)):
            with self.subTest(field=field):
                app.slider(key=self.key(app, field, 2)).set_value(value).run()
                expected_png = app.session_state["creator_render"].png
                original = getattr(second, field)
                if field in ("x", "y", "width", "height"):
                    original *= 100
                app.slider(key=self.key(app, field, 2)).set_value(original).run()
                app.number_input(key=self.key(app, field + "_number", 2)).set_value(value).run()
                self.assertEqual(app.session_state["creator_render"].png, expected_png)
                self.assertEqual(self.download.call_args.kwargs["data"], expected_png)
                self.assertEqual(app.session_state["creator_draft"].image_layers[0], first)
                self.assertFalse(app.exception)

    def test_numeric_values_survive_navigation_replacement_and_cleanup(self):
        app = self.app()
        self.add(app)
        number_key = self.key(app, "x_number")
        app.number_input(key=number_key).set_value(-29.0).run()
        self.files[self.key(app, "upload")] = creator_tests.upload("green")
        app.run()
        self.assertEqual(app.number_input(key=number_key).value, -29.0)
        self.files.clear()
        app.button(key="home").click().run()
        app.button(key="create").click().run()
        self.assertEqual(app.number_input(key=number_key).value, -29.0)
        self.assertEqual(app.slider(key=self.key(app, "x")).value, -29.0)
        revision = app.session_state["creator_draft"].revision
        app.run()
        self.assertEqual(app.session_state["creator_draft"].revision, revision)
        app.button(key=self.key(app, "remove")).click().run()
        self.assertNotIn(number_key, app.session_state)
        self.add(app)
        app.button(key="creator_clear").click().run()
        self.assertFalse(any(k.startswith("creator_image_") for k in app.session_state.filtered_state))

    def test_remove_does_not_change_other_image_ids_or_captions(self):
        app = self.app()
        self.add(app)
        self.add(app, "green")
        app.button(key=self.key(app, "remove", 1)).click().run()
        self.assertEqual([l.id for l in app.session_state["creator_draft"].image_layers], [2])
        self.add(app)
        self.assertEqual([l.id for l in app.session_state["creator_draft"].image_layers], [2, 3])
        self.assertEqual([c.id for c in app.session_state["creator_draft"].captions], [1])

    def test_limit_and_cancel_pending_upload(self):
        app = self.app()
        app.button(key="creator_add_image").click().run()
        self.assertNotIn("creator_render", app.session_state)
        self.assertFalse(app.get("download_button"))
        app.button(key=self.key(app, "remove")).click().run()
        for _ in range(8):
            self.add(app)
        self.assertTrue(app.button(key="creator_add_image").disabled)

    def test_replacement_preserves_placement_and_changes_export(self):
        app = self.app()
        self.add(app)
        app.slider(key=self.key(app, "x")).set_value(40.0).run()
        old = app.session_state["creator_render"].png
        self.files[self.key(app, "upload")] = creator_tests.upload("green")
        app.run()
        self.assertEqual(app.session_state["creator_draft"].image_layers[0].x, 0.4)
        self.assertNotEqual(app.session_state["creator_render"].png, old)

    def test_invalid_replacement_blocks_stale_download_until_corrected(self):
        app = self.app()
        self.add(app)
        self.files[self.key(app, "upload")] = BytesIO(b"bad")
        app.run()
        self.assertTrue(app.error)
        self.assertNotIn("creator_render", app.session_state)
        self.assertFalse(app.get("download_button"))
        app.run()
        self.assertTrue(app.error)
        self.files[self.key(app, "upload")] = creator_tests.upload("green")
        app.run()
        self.assertFalse(app.error)
        self.assertIn("creator_render", app.session_state)

    def test_image_render_failure_blocks_stale_download(self):
        app = self.app()
        self.add(app)
        self.render.side_effect = RenderingError("Image unavailable")
        app.slider(key=self.key(app, "opacity")).set_value(40).run()
        self.assertTrue(app.error)
        self.assertNotIn("creator_render", app.session_state)
        self.assertFalse(app.get("download_button"))

    def test_navigation_preserves_layers_even_when_upload_widgets_disappear(self):
        app = self.app()
        self.add(app)
        before = app.session_state["creator_draft"].image_layers
        self.files.clear()
        app.button(key="home").click().run()
        app.button(key="create").click().run()
        self.assertEqual(app.session_state["creator_draft"].image_layers, before)
        self.assertIn("creator_render", app.session_state)
        self.assertFalse(app.exception)

    def test_clear_and_base_replacement_remove_all_layer_state(self):
        app = self.app()
        self.add(app)
        old_upload_key = self.key(app, "upload")
        self.files["creator_upload_0"] = creator_tests.upload("green")
        app.run()
        self.assertEqual(app.session_state["creator_draft"].image_layers, ())
        self.assertNotIn(old_upload_key, app.session_state)
        self.assertNotEqual(self.key(app, "upload"), old_upload_key)
        self.add(app)
        app.button(key="creator_clear").click().run()
        self.assertNotIn("creator_draft", app.session_state)
        self.assertNotIn("creator_render", app.session_state)
        self.assertFalse(any(k.startswith("creator_image_") for k in app.session_state.filtered_state))

    def test_explicit_upload_removal_removes_layer(self):
        app = self.app()
        self.add(app)
        self.files.pop(self.key(app, "upload"))
        app.session_state[self.key(app, "changed")] = True
        app.run()
        self.assertEqual(app.session_state["creator_draft"].image_layers, ())
        self.assertFalse(app.exception)

    def test_logout_and_expiry_cleanup_leave_v3_policy_intact(self):
        app = self.app()
        self.add(app)
        for expired in (False, True):
            state, client, _ = make_state()
            state.update(app.session_state.filtered_state)
            state["v3_text"] = "private V3 text"
            state["query"] = "preserve query"
            if expired:
                client.auth.get_session.return_value = None
                current_account(state)
            else:
                logout(state)
            self.assertNotIn("creator_draft", state)
            self.assertNotIn("creator_render", state)
            self.assertNotIn("v3_text", state)
            self.assertEqual(state["creator_generation"], 1)
            self.assertEqual(state["query"], "preserve query")

    def test_no_external_calls_or_v3_state_changes(self):
        state, client, _ = make_state()
        app = self.app()
        app.session_state[ACCOUNT_KEY] = state[ACCOUNT_KEY]
        app.session_state["v3_text"] = "untouched"
        with patch("utils.library.fetch_library") as library:
            self.add(app)
            app.slider(key=self.key(app, "opacity")).set_value(20).run()
            app.button(key=self.key(app, "remove")).click().run()
            library.assert_not_called()
        self.assertEqual(app.session_state["v3_text"], "untouched")
        client.table.assert_not_called()
        client.auth.get_session.assert_not_called()
        for guard in self.guards:
            guard.assert_not_called()


if __name__ == "__main__":
    unittest.main()
