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
        self.assertEqual(sum(c.value == "Preview unavailable" for c in app.caption), 40)
        app.text_input[0].set_value("2 choices").run()
        self.assertFalse(app.exception)
        headings = [h.value for h in app.subheader]
        self.assertLess(headings.index("Two Buttons"), headings.index("Drake Hotline Bling"))
        text = "\n".join(item.value for item in app.markdown)
        self.assertIn("Struggling to choose", text)
        self.assertIn("Common situations", text)
        self.assertIn("Categories", text)
        self.assertTrue(any(c.value.startswith("Also known as:") for c in app.caption))
        self.assertTrue(any(c.value.startswith("Keywords:") for c in app.caption))

    @patch("utils.images.load_preview", return_value=b"invalid image")
    def test_corrupt_images_keep_results(self, preview):
        app = AppTest.from_file(str(APP_PATH)).run()
        self.assertFalse(app.exception)
        self.assertEqual(sum(c.value == "Preview unavailable" for c in app.caption), 40)
        self.assertIn("Stonks", [h.value for h in app.subheader])

    @patch("utils.images.load_preview")
    def test_valid_images_render(self, preview):
        buffer = BytesIO()
        Image.new("RGB", (20, 20), "red").save(buffer, format="PNG")
        preview.return_value = buffer.getvalue()
        app = AppTest.from_file(str(APP_PATH)).run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.get("image")), 40)
        self.assertFalse(any(c.value == "Preview unavailable" for c in app.caption))


if __name__ == "__main__":
    unittest.main()
