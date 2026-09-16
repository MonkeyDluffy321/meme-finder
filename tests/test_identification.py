import unittest
from unittest.mock import patch
from PIL import Image

from utils.identification import identify


class IdentificationTests(unittest.TestCase):
    def setUp(self):
        self.image = Image.new("RGB", (20, 20))
        patch("utils.identification.informative", return_value=True).start()
        patch("utils.identification.image_hash", return_value="1" * 256).start()
        self.addCleanup(patch.stopall)

    def rows(self, matches):
        return [{"id": str(i), "hash": "1" * n + "0" * (256-n)} for i, n in enumerate(matches)]

    def test_clear_hash_match(self):
        result = identify(self.image, self.rows([256, 160]))
        self.assertEqual(result.status, "likely")
        self.assertEqual(result.candidates[0]["id"], "0")

    def test_weak_unknown_and_tied(self):
        for matches, status in [([225, 200], "possible"), ([170, 150], "unknown"),
                                 ([256, 256], "possible"), ([256], "possible")]:
            self.assertEqual(identify(self.image, self.rows(matches)).status, status)

    def test_no_references_is_unavailable(self):
        self.assertEqual(identify(self.image, []).status, "unavailable")

    def test_blank_image_is_unknown(self):
        with patch("utils.identification.informative", return_value=False):
            self.assertEqual(identify(self.image, self.rows([256])).status, "unknown")

    def test_visual_match(self):
        rows = self.rows([210, 150])
        rows[0]["embedding"], rows[1]["embedding"] = [1, 0], [0, 1]
        result = identify(self.image, rows, [1, 0])
        self.assertEqual(result.status, "likely")
        self.assertEqual(result.mode, "visual + hash")

    def test_invalid_or_partial_embeddings_use_hash(self):
        for vector in ([float("nan"), 0], [0, 0], [1]):
            rows = self.rows([256, 150])
            for row in rows:
                row["embedding"] = [1, 0]
            self.assertEqual(identify(self.image, rows, vector).mode, "hash-only")
        rows[1].pop("embedding")
        self.assertEqual(identify(self.image, rows, [1, 0]).mode, "hash-only")
