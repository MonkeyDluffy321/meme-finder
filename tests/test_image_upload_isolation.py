"""Use actual Streamlit uploader serialization and callbacks, not uploader mocks."""

from io import BytesIO
from pathlib import Path
import unittest
from unittest.mock import patch

from PIL import Image
from streamlit.testing.v1 import AppTest

from utils.creator import ImageLayer


APP = Path(__file__).resolve().parents[1] / "app.py"


def picture(color):
    buffer = BytesIO()
    Image.new("RGB", (100, 80), color).save(buffer, format="PNG")
    return buffer.getvalue()


class ImageUploadIsolationTests(unittest.TestCase):
    def setUp(self):
        self.guards = [patch(target, side_effect=AssertionError("External service must not run")).start()
                       for target in ("utils.images.load_preview", "utils.vision.read_api_key",
                                      "utils.vision.GeminiProvider.explain", "utils.ocr.extract_text",
                                      "utils.library.fetch_library", "utils.library.save_meme",
                                      "utils.library.record_view")]
        self.addCleanup(patch.stopall)
        self.app = AppTest.from_file(str(APP))
        self.app.session_state["creator_active"] = True
        self.app.run()
        self.app.file_uploader(key="creator_upload_0").set_value(("base.png", picture("gray"), "image/png")).run()
        self.assertFalse(self.app.exception)

    def uploader(self, layer_id):
        return next(widget for widget in self.app.file_uploader if widget.label == f"Upload image {layer_id}")

    def layers(self):
        return {layer.id: layer for layer in self.app.session_state["creator_draft"].image_layers}

    def control(self, layer_id, field):
        return next(widget for widget in self.app.slider if widget.key.endswith(f"_{layer_id}_{field}"))

    def test_two_native_uploaders_replace_remove_and_keys(self):
        app = self.app
        app.button(key="creator_add_image").click().run()
        self.uploader(1).set_value(("same-name.png", picture("red"), "image/png")).run()
        self.control(1, "x").set_value(25.0).run()
        self.control(1, "opacity").set_value(60).run()
        first = self.layers()[1]
        app.button(key="creator_add_image").click().run()
        first_key, second_key = self.uploader(1).key, self.uploader(2).key
        self.assertNotEqual(first_key, second_key)
        self.assertTrue(first_key.endswith("_1_upload"))
        self.assertTrue(second_key.endswith("_2_upload"))
        self.uploader(2).set_value(("same-name.png", picture("blue"), "image/png")).run()
        self.assertEqual(self.layers()[1], first)
        self.assertEqual(self.layers()[2].image_png, ImageLayer(2, picture("blue")).image_png)
        self.control(2, "x").set_value(50.0).run()
        self.control(2, "rotation").set_value(30.0).run()
        self.uploader(2).set_value(("same-name.png", picture("green"), "image/png")).run()
        self.assertEqual(self.layers()[1], first)
        self.assertEqual(self.layers()[2].image_png, ImageLayer(2, picture("green")).image_png)
        self.assertEqual((self.layers()[2].x, self.layers()[2].rotation), (0.5, 30))
        second = self.layers()[2]
        next(button for button in app.button if button.label == "Remove image 1").click().run()
        self.assertEqual(self.layers(), {2: second})
        self.assertEqual(self.uploader(2).key, second_key)
        self.assertEqual(self.uploader(2).value.getvalue(), picture("green"))
        self.assertEqual(self.control(2, "x").value, 50.0)
        self.assertEqual(self.control(2, "rotation").value, 30.0)
        self.assertFalse(app.exception)
        for guard in self.guards:
            guard.assert_not_called()

    def test_default_placement_keeps_both_sources_visible(self):
        app = self.app
        app.button(key="creator_add_image").click().run()
        self.uploader(1).set_value(("a.png", picture("red"), "image/png")).run()
        first = self.layers()[1]
        app.button(key="creator_add_image").click().run()
        self.uploader(2).set_value(("b.png", picture("blue"), "image/png")).run()
        self.assertEqual(self.layers()[1], first)
        self.assertNotEqual((self.layers()[2].x, self.layers()[2].y), (first.x, first.y))
        with Image.open(BytesIO(app.session_state["creator_render"].png)) as rendered:
            colors = {color for _, color in rendered.getcolors(rendered.width * rendered.height)}
        self.assertIn((255, 0, 0), colors)
        self.assertIn((0, 0, 255), colors)

    def test_clear_second_uploader_does_not_remove_first(self):
        app = self.app
        for layer_id, color in ((1, "red"), (2, "blue")):
            app.button(key="creator_add_image").click().run()
            self.uploader(layer_id).set_value(("image.png", picture(color), "image/png")).run()
        first = self.layers()[1]
        self.uploader(2).clear().run()
        self.assertEqual(self.layers(), {1: first})
        app.button(key="creator_add_image").click().run()
        self.assertEqual([widget.label for widget in app.file_uploader],
                         ["Creator image", "Upload image 1", "Upload image 3"])
        self.uploader(3).set_value(("image.png", picture("green"), "image/png")).run()
        self.assertEqual(self.layers()[1], first)
        self.assertEqual(set(self.layers()), {1, 3})
        self.assertFalse(app.exception)


if __name__ == "__main__":
    unittest.main()
