from copy import deepcopy
import unittest

from utils.search import metadata_items, normalize_hinglish_query, search_memes


class HinglishTests(unittest.TestCase):
    def test_generic_query_recovery(self):
        rows = [{"name": "Pain Clinic"}, {"name": "Fire Alarm"}, {"name": "Two Doors"}]
        for query, name in [("dard wali clinic", "Pain Clinic"),
                            ("jal raha hai alarm", "Fire Alarm"),
                            ("do doors mein", "Two Doors")]:
            with self.subTest(query=query):
                self.assertEqual(search_memes(rows, query, use_semantic=False,
                                              require_strong=True)[0]["name"], name)

    def test_unknown_words_and_negation_survive(self):
        self.assertEqual(normalize_hinglish_query("dard wali xyz nahi not never"),
                         "pain xyz nahi not never")
        for query in ("do work", "mein", "wali", "hai", "do not enter"):
            self.assertEqual(normalize_hinglish_query(query), query)
        self.assertEqual(normalize_hinglish_query("raha hai"), "raha hai")
        self.assertEqual(search_memes([{"name": "Other"}], "raha hai", use_semantic=False), [])
        self.assertEqual(search_memes([{"name": "Pain Clinic"}],
                                     "dard wali xyz qwerty", use_semantic=False,
                                     require_strong=True), [])

    def test_metadata_original_identity_and_idempotence(self):
        rows = [{"name": "Dard Wali"}, {"name": "Pain"}]
        original = deepcopy(rows)
        metadata = list(metadata_items(rows[0]))
        self.assertIs(search_memes(rows, "Dard Wali", use_semantic=False)[0], rows[0])
        self.assertEqual(rows, original)
        self.assertEqual(list(metadata_items(rows[0])), metadata)
        for query in ("do doors mein", "dard wali clinic", "jal raha hai alarm"):
            normalized = normalize_hinglish_query(query)
            self.assertEqual(normalize_hinglish_query(normalized), normalized)
