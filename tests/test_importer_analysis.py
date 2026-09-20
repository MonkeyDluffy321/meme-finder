from io import BytesIO
import unittest
from unittest.mock import Mock, patch

from PIL import Image

from utils.importer_analysis import FIELDS, suggest_metadata
from utils.identification import Identification
from utils.ocr import OCRResult
from utils.vision import Explanation, VisionResult


class MetadataAnalysisTests(unittest.TestCase):
    def setUp(self):
        buffer = BytesIO()
        Image.new("RGB", (12, 12)).save(buffer, format="PNG")
        self.content = buffer.getvalue()
        self.meme = dict(id="test", name="Known Meme", meaning="Template meaning",
                         keywords=["testing"], situations=["testing software"],
                         emotions=["joy"], categories=["work"], aliases=["Test Meme"])
        self.local = {"ocr": OCRResult("ok", "caption"),
                      "identification": Identification("likely", [{"id": "test"}])}
        self.vision = VisionResult("ok", Explanation("A person at work", "Feeling joy at work",
                                                      "A happy reaction", [], "Context is limited"))

    def test_indexer_supplies_provider_without_ui_secrets(self):
        provider = Mock()
        provider.explain.return_value = self.vision
        with patch("utils.importer_analysis.analyze", return_value=self.local), \
                patch("utils.vision.read_api_key", side_effect=AssertionError("UI secrets accessed")):
            suggestions, _ = suggest_metadata(self.content, [self.meme], provider=provider)
        provider.explain.assert_called_once()
        self.assertEqual(suggestions["meaning"], "Feeling joy at work")

    def test_provider_failure_preserves_reference_metadata(self):
        from copy import deepcopy
        before = deepcopy(self.meme)
        provider = Mock()
        provider.explain.side_effect = RuntimeError("offline")
        with patch("utils.importer_analysis.analyze", return_value=self.local):
            suggestions, notice = suggest_metadata(self.content, [self.meme], provider=provider)
        self.assertEqual(suggestions["meaning"], before["meaning"])
        self.assertEqual(self.meme, before)
        self.assertIn("unavailable", notice)

    def test_metadata_suggestions_reuse_pipeline(self):
        with patch("utils.importer_analysis.analyze", return_value=self.local) as analyze, \
                patch("utils.importer_analysis.explain_upload", return_value=self.vision) as explain:
            suggestions, _ = suggest_metadata(self.content, [self.meme])
        self.assertEqual(set(suggestions), set(FIELDS))
        self.assertEqual(suggestions["meaning"], "Feeling joy at work")
        self.assertEqual(suggestions["name"], "Known Meme")
        self.assertEqual(suggestions["aliases"], ["Test Meme"])
        self.assertEqual(analyze.call_args.args[0].image.mode, "RGB")
        self.assertEqual(explain.call_args.args[1], self.local)

    def test_unknown_image_uses_vision_without_inventing_identity(self):
        self.local["identification"] = Identification("unknown")
        with patch("utils.importer_analysis.analyze", return_value=self.local), \
                patch("utils.importer_analysis.explain_upload", return_value=self.vision):
            suggestions, _ = suggest_metadata(self.content, [self.meme])
        self.assertNotIn("name", suggestions)
        self.assertNotIn("aliases", suggestions)
        self.assertEqual(suggestions["categories"], ["work"])
        self.assertEqual(suggestions["emotions"], ["joy"])
        self.assertTrue(suggestions["keywords"])
        self.assertTrue(suggestions["situations"])

    def test_unavailable_analysis_is_non_destructive(self):
        self.local["identification"] = Identification("unknown")
        with patch("utils.importer_analysis.analyze", return_value=self.local), \
                patch("utils.importer_analysis.explain_upload", return_value=VisionResult("timeout")):
            suggestions, notice = suggest_metadata(self.content, [self.meme])
        self.assertEqual(suggestions, {})
        self.assertIn("unavailable", notice)
