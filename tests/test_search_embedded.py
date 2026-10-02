import json
from pathlib import Path
import unittest

from utils.search import _embedded_identity, search_memes


class EmbeddedIdentityTests(unittest.TestCase):
    def setUp(self):
        self.rows = [{"name": "Quiet Harbor", "aliases": ["Calm Port"],
                      "keywords": ["storm", "fire"]}]

    def test_catalog_name_and_alias_with_supported_context(self):
        for query in ("storm but quiet harbor", "storm but CALM PORT",
                      "jal raha hai but quiet harbor"):
            with self.subTest(query=query):
                self.assertEqual(_embedded_identity(self.rows, query), self.rows)

    def test_negation_unknown_context_and_incomplete_identity(self):
        for query in ("storm but not quiet harbor", "storm but quiet harbor nahi",
                      "don't show quiet harbor storm", "storm but quiet harbor nahin",
                      "never quiet harbor storm", "storm but quiet harbor xyz",
                      "xyz quiet harbor", "quiet harbor please", "storm quiet",
                      "storm quiet harbors"):
            with self.subTest(query=query):
                self.assertEqual(_embedded_identity(self.rows, query), [])

    def test_competing_and_duplicate_identities_abstain(self):
        for extra, query in [({"name": "Other Port"}, "storm quiet harbor other port"),
                             ({"name": "Other", "aliases": ["Quiet Harbor"]}, "storm quiet harbor"),
                             ({"name": "Harbor"}, "storm quiet harbor")]:
            self.assertEqual(_embedded_identity(self.rows + [extra], query), [])
        self.assertEqual(_embedded_identity([{"name": "Harbor", "keywords": ["storm"]}],
                                            "storm harbor"), [])

    def test_fallback_integration_and_existing_exact_behavior(self):
        catalog = json.loads((Path(__file__).resolve().parents[1] / "data/memes.json").read_text(encoding="utf-8"))
        result = search_memes(catalog, "sab jal raha hai but this is fine",
                              use_semantic=False, require_strong=True)
        self.assertEqual([r["id"] for r in result], ["this-is-fine"])
        self.assertEqual(search_memes(self.rows, "Quiet Harbor", use_semantic=False), self.rows)
        query = "xyz qwerty storm but not quiet harbor"
        self.assertEqual(search_memes(self.rows, query, use_semantic=False, require_strong=True), [])
