from io import BytesIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image
from streamlit.testing.v1 import AppTest

from utils.importer import ImportError, import_meme, meme_id, normalize_list
from utils.search import search_memes
from utils.uploads import MAX_BYTES


class ImporterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "memes.json").write_text("[]", encoding="utf-8")
        self.target = self.root / "imported_memes.json"
        self.metadata = dict(name="Wasting Potential", meaning="Avoiding work",
                             keywords="potential, procrastination", situations="avoiding work",
                             emotions="regret", categories="work", aliases="")
        buffer = BytesIO()
        Image.new("RGB", (20, 20), "red").save(buffer, format="JPEG")
        self.content = buffer.getvalue()

    def save(self):
        return import_meme(self.metadata, self.content, data_dir=self.root)

    def test_ids_and_normalization(self):
        self.assertEqual(meme_id(" Wasting Potential! "), "wasting-potential")
        self.assertEqual(meme_id("Café"), "cafe")
        self.assertEqual(normalize_list(" work, WORK,  avoiding   work, ,"),
                         ["work", "avoiding work"])
        with self.assertRaises(ImportError):
            meme_id("../!")

    def test_valid_persistence_and_search(self):
        record = self.save()
        records = json.loads(self.target.read_text(encoding="utf-8"))
        self.assertEqual(records, [record])
        self.assertEqual(record["description"], record["meaning"])
        self.assertNotIn("image_url", record)
        with Image.open(self.root / "imported_images" / record["local_image"]) as image:
            self.assertEqual(image.format, "PNG")
            self.assertEqual(image.mode, "RGB")
        self.assertEqual(search_memes(records, "wasting potential")[0]["id"], record["id"])
        self.metadata["name"] = "Another Meme"
        self.save()
        self.assertEqual(len(json.loads(self.target.read_text())), 2)

    def test_duplicates_in_both_datasets(self):
        record = self.save()
        before = self.target.read_bytes()
        with self.assertRaisesRegex(ImportError, "already exists"):
            self.save()
        self.assertEqual(self.target.read_bytes(), before)
        (self.root / "memes.json").write_text(json.dumps([record]))
        self.target.write_text("[]")
        with self.assertRaisesRegex(ImportError, "already exists"):
            self.save()
        self.assertEqual(len(list((self.root / "imported_images").iterdir())), 1)

    def test_malformed_collection_is_unchanged(self):
        for content in ("{", "{}", "[1]", '[{"id":"bad"}]'):
            with self.subTest(content=content):
                self.target.write_text(content)
                with self.assertRaises(ImportError):
                    self.save()
                self.assertEqual(self.target.read_text(), content)
                self.assertFalse((self.root / "imported_images").exists())

    def test_blank_required_fields(self):
        for field in ("name", "meaning", "keywords", "situations", "emotions", "categories"):
            with self.subTest(field=field), patch.dict(self.metadata, {field: "  "}):
                with self.assertRaisesRegex(ImportError, "required"):
                    self.save()

    def test_bad_and_oversized_images(self):
        for content in (b"", b"broken", b"x" * (MAX_BYTES + 1)):
            self.content = content
            with self.assertRaises(ImportError):
                self.save()
        buffer = BytesIO()
        Image.new("RGB", (10, 10)).save(buffer, format="GIF")
        self.content = buffer.getvalue()
        with self.assertRaisesRegex(ImportError, "JPEG"):
            self.save()
        self.assertFalse(self.target.exists())

    def test_safe_filename(self):
        self.metadata["name"] = '../../CON \\ nested:evil.jpg'
        record = self.save()
        filename = record["local_image"]
        self.assertRegex(filename, r"^[a-z0-9-]+\.png$")
        self.assertEqual((self.root / "imported_images" / filename).resolve().parent,
                         (self.root / "imported_images").resolve())

    def test_atomic_replace_failure_rolls_back(self):
        self.target.write_text("[]")
        with patch("utils.importer.os.replace", side_effect=OSError("disk full")):
            with self.assertRaisesRegex(ImportError, "Could not save"):
                self.save()
        self.assertEqual(self.target.read_text(), "[]")
        self.assertEqual(list((self.root / "imported_images").iterdir()), [])
        self.assertEqual(list(self.root.glob(".import-*")), [])
        self.assertFalse((self.root / ".meme-import.lock").exists())

    def test_concurrent_import_rejected(self):
        (self.root / ".meme-import.lock").touch()
        with self.assertRaisesRegex(ImportError, "in progress"):
            self.save()
        self.assertFalse(self.target.exists())

    @patch("utils.images.load_preview", return_value=None)
    def test_app_dialog_validation_and_success(self, preview):
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py")).run()
        app.button(key="import_meme").click().run()
        self.assertFalse(app.exception)
        submit = next(b for b in app.button if b.label == "Import")
        # AppTest executes full scripts instead of browser dialog fragments.
        app.button(key="import_meme").click()
        submit.click().run()
        self.assertTrue(any("Name is required" in e.value for e in app.error))
        # AppTest cannot upload files; exercise submission/rerun using the real
        # importer with fixture image bytes and isolated on-disk collections.
        app.text_input(key="importer_name").set_value("Wasting Potential")
        def save_fixture(*args, **kwargs):
            return self.save()
        original_read = Path.read_text
        actual_imports = Path(__file__).resolve().parents[1] / "data" / "imported_memes.json"
        def read_collection(path, *args, **kwargs):
            if path == actual_imports:
                return original_read(self.target, *args, **kwargs) if self.target.exists() else "[]"
            return original_read(path, *args, **kwargs)
        with patch("utils.importer_ui.import_meme", side_effect=save_fixture), \
                patch.object(Path, "read_text", read_collection):
            app.button(key="import_meme").click()
            next(b for b in app.button if b.label == "Import").click().run()
            self.assertFalse(app.exception)
            self.assertTrue(any("Imported Wasting Potential" in s.value for s in app.success))
            app.text_input(key="query").set_value("wasting potential").run()
            self.assertFalse(app.exception)
            self.assertIn("Wasting Potential", [s.value for s in app.subheader])


if __name__ == "__main__":
    unittest.main()
