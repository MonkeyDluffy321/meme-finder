from io import BytesIO
from tempfile import TemporaryDirectory
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from utils.intelligence import analyze
from utils.local_explainer import explain_local
from utils.ocr import OCRResult
from utils.template_index import load_collection, read_index, reference_path
from utils.uploads import validate_upload


class ReferenceExplanationTests(TestCase):
    def test_reference_and_transcoded_uploads(self):
        memes = load_collection()
        for key, caption in [("success-kid", ""), ("wasting-potential",
                "I love wasting my potential, it's my favorite hobby.")]:
            meme = next(m for m in memes if m["id"] == key)
            path = reference_path(meme)
            if not path.exists():
                self.skipTest("Local reference unavailable: " + key)
            original = validate_upload(path.read_bytes())
            jpeg = BytesIO()
            original.image.resize((320, 320)).save(jpeg, "JPEG", quality=75)
            for upload, exact in [(original, True), (validate_upload(jpeg.getvalue()), False)]:
                with self.subTest(key=key, exact=exact), patch("utils.intelligence.extract_text",
                        return_value=OCRResult("ok", caption)):
                    result = analyze(upload, memes)
                    identity = result["identification"]
                    self.assertEqual(identity.status, "likely")
                    self.assertEqual(identity.mode == "exact pixels", exact)
                    explanation = explain_local(result, memes).explanation
                    self.assertEqual(explanation.template_name, meme["name"])
                    self.assertIn(meme["meaning"], explanation.expression)
                    self.assertEqual(explanation.situations, meme["situations"])
                    if caption:
                        self.assertIn("ironic", explanation.why_it_works)
                        self.assertNotIn(caption, explanation.answer)

    def test_missing_index_recovers_imported_image_without_writes(self):
        meme = next(m for m in load_collection() if m["id"] == "wasting-potential")
        with TemporaryDirectory() as directory:
            cache = Path(directory)
            self.assertEqual([r["id"] for r in read_index([meme], cache)], [meme["id"]])
            self.assertEqual(list(cache.iterdir()), [])
