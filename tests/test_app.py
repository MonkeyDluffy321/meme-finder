from io import BytesIO
from pathlib import Path
import unittest
from unittest.mock import patch

from PIL import Image
from streamlit.testing.v1 import AppTest


APP_PATH = Path(__file__).resolve().parents[1] / "app.py"


class AppTests(unittest.TestCase):
    @patch("utils.images.load_preview", return_value=None)
    def test_unavailable_images_keep_text_and_search(self, preview):
        app = AppTest.from_file(str(APP_PATH)).run()
        self.assertFalse(app.exception)
        self.assertEqual(sum(c.value == "Preview unavailable" for c in app.caption), 6)
        app.text_input[0].set_value("2 choices").run()
        self.assertFalse(app.exception)
        headings = [h.value for h in app.subheader]
        self.assertLess(headings.index("Two Buttons"), headings.index("Drake Hotline Bling"))
        text = "\n".join(item.value for item in app.markdown)
        self.assertIn("Struggling to choose", text)
        self.assertIn("Common situations", text)
        self.assertTrue(any(c.value.startswith("Categories:") for c in app.caption))
        self.assertTrue(any(c.value.startswith("Also known as:") for c in app.caption))
        self.assertTrue(any(c.value.startswith("Keywords:") for c in app.caption))

    @patch("utils.images.load_preview", return_value=b"invalid image")
    def test_corrupt_images_keep_results(self, preview):
        app = AppTest.from_file(str(APP_PATH)).run()
        self.assertFalse(app.exception)
        self.assertEqual(sum(c.value == "Preview unavailable" for c in app.caption), 6)
        self.assertIn("Distracted Boyfriend", [h.value for h in app.subheader])

    @patch("utils.images.load_preview")
    def test_valid_images_render(self, preview):
        images = []
        for size in [(20, 20), (1200, 200), (200, 1200)] * 2:
            buffer = BytesIO()
            Image.new("RGB", size, "red").save(buffer, format="PNG")
            images.append(buffer.getvalue())
        preview.side_effect = images
        app = AppTest.from_file(str(APP_PATH)).run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.get("image")), 6)
        self.assertFalse(any(c.value == "Preview unavailable" for c in app.caption))

    @patch("utils.images.load_preview", return_value=None)
    def test_secondary_metadata_is_in_collapsed_details(self, preview):
        app = AppTest.from_file(str(APP_PATH)).run()
        self.assertFalse(app.exception)
        details = [item for item in app.expander if item.label == "More details"]
        self.assertEqual(len(details), 6)
        for item in details:
            self.assertFalse(item.proto.expanded)
            captions = [caption.value for caption in item.caption]
            self.assertTrue(any(value.startswith("Also known as:") for value in captions))
            self.assertTrue(any(value.startswith("Keywords:") for value in captions))
            self.assertTrue(any("Common situations" in text.value for text in item.markdown))
            self.assertTrue(any(value.startswith("Categories:") for value in captions))
            self.assertTrue(any(value.startswith("Emotions:") for value in captions))
        self.assertEqual(sum(c.value.startswith("Categories:") for c in app.caption), 6)
        self.assertEqual(sum(c.value.startswith("Emotions:") for c in app.caption), 6)

    @patch("utils.images.load_preview", return_value=None)
    def test_filters_combine_with_search_and_reset(self, preview):
        app = AppTest.from_file(str(APP_PATH)).run()
        app.text_input[0].set_value("reaction").run()
        app.multiselect(key="categories").set_value(["conflict"]).run()
        self.assertFalse(app.exception)
        self.assertIn("Batman Slapping Robin", [h.value for h in app.subheader])
        self.assertNotIn("Surprised Pikachu", [h.value for h in app.subheader])
        app.multiselect(key="emotions").set_value(["anger"]).run()
        self.assertIn("Batman Slapping Robin", [h.value for h in app.subheader])
        app.button(key="reset_filters").click().run()
        self.assertEqual(app.multiselect(key="categories").value, [])
        self.assertEqual(app.multiselect(key="emotions").value, [])
        self.assertEqual(app.text_input[0].value, "reaction")

    @patch("utils.images.load_preview", return_value=None)
    def test_empty_states(self, preview):
        app = AppTest.from_file(str(APP_PATH)).run()
        app.text_input[0].set_value("zxqv jklz").run()
        self.assertFalse(app.exception)
        self.assertIn("No meme matched that description", app.info[0].value)
        app.text_input[0].set_value("distracted boyfriend").run()
        app.multiselect(key="categories").set_value(["money"]).run()
        self.assertFalse(app.exception)
        self.assertIn("No templates match these filters", app.info[0].value)

    @patch("utils.images.load_preview", return_value=None)
    def test_pagination_and_query_reset(self, preview):
        app = AppTest.from_file(str(APP_PATH)).run()
        self.assertTrue(app.button(key="previous").disabled)
        app.button(key="next").click().run()
        self.assertNotIn("Distracted Boyfriend", [h.value for h in app.subheader])
        self.assertEqual(app.session_state["page"], 1)
        app.text_input[0].set_value("2 choices").run()
        self.assertEqual(app.session_state["page"], 0)
        app.button(key="clear_search").click().run()
        self.assertEqual(app.text_input[0].value, "")
        self.assertIn("Distracted Boyfriend", [h.value for h in app.subheader])

    @patch("utils.images.load_preview", return_value=None)
    def test_quick_filters_and_home(self, preview):
        app = AppTest.from_file(str(APP_PATH)).run()
        app.pills(key="quick_category").set_value("reaction").run()
        self.assertFalse(app.exception)
        self.assertEqual(app.multiselect(key="categories").value, ["reaction"])
        app.pills(key="quick_emotion").set_value("anger").run()
        self.assertFalse(app.exception)
        self.assertEqual(app.multiselect(key="emotions").value, ["anger"])
        self.assertIn("Batman Slapping Robin", [h.value for h in app.subheader])
        app.button(key="home").click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.multiselect(key="categories").value, [])
        self.assertEqual(app.multiselect(key="emotions").value, [])
        self.assertEqual(app.session_state["page"], 0)
        self.assertEqual(app.text_input[0].value, "")

    @patch("utils.images.load_preview", return_value=None)
    def test_navigation_placeholders_are_disabled(self, preview):
        app = AppTest.from_file(str(APP_PATH)).run()
        for label in ["Explore", "Categories", "Saved", "Recently Viewed"]:
            button = next(button for button in app.button if button.label == label)
            self.assertTrue(button.disabled)

    @patch("utils.images.load_preview", return_value=None)
    def test_search_button_keeps_results(self, preview):
        app = AppTest.from_file(str(APP_PATH)).run()
        app.text_input[0].set_value("2 choices").run()
        before = [h.value for h in app.subheader]
        next(button for button in app.button if button.label == "Search").click().run()
        self.assertFalse(app.exception)
        self.assertEqual([h.value for h in app.subheader], before)


if __name__ == "__main__":
    unittest.main()
