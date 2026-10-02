"""Evaluator correctness tests; search-quality failures are measurements, not test failures."""

from contextlib import ExitStack, redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from utils import search_eval as evaluation


def case(identity, relevant, **extra):
    return dict(id=identity, category="ambiguous", query=identity, target="templates",
                relevant_ids=relevant, abstain=not relevant, **extra)


class EvaluationMetricsTests(unittest.TestCase):
    def test_hand_calculated_metrics_and_cutoff(self):
        rows = [
            evaluation.score_case(case("hit", ["a"]), ["a"]),
            evaluation.score_case(case("partial", ["a", "b"]), ["x", "a", "y", "b"]),
            evaluation.score_case(case("miss", ["a"]), []),
            evaluation.score_case(case("abstain", []), []),
            evaluation.score_case(case("noise", []), ["z"]),
        ]
        metrics = evaluation.summarize(rows)
        self.assertEqual((metrics["total"], metrics["passed"], metrics["failed"]), (5, 2, 3))
        self.assertAlmostEqual(metrics["top1_accuracy"], 1 / 3)
        self.assertAlmostEqual(metrics["top3_recall"], 0.5)
        self.assertEqual(metrics["abstention_accuracy"], 0.5)
        self.assertEqual((metrics["noise_count"], metrics["returned_at_3"]), (3, 5))
        self.assertEqual(metrics["noise_rate"], 0.6)
        self.assertEqual(rows[1]["returned_ids"], ["x", "a", "y", "b"])

    def test_multiple_relevant_records_and_strict_pass(self):
        sample = case("multi", ["a", "b"])
        self.assertTrue(evaluation.score_case(sample, ["b", "a"])["passed"])
        partial = evaluation.score_case(sample, ["a"])
        self.assertTrue(partial["top1"])
        self.assertEqual(partial["recall3"], 0.5)
        self.assertFalse(partial["passed"])
        self.assertFalse(evaluation.score_case(sample, ["a", "b", "noise"])["passed"])
        with self.assertRaises(ValueError):
            evaluation.score_case(sample, ["a", "a"])

    def test_empty_denominators_are_not_perfect_scores(self):
        metrics = evaluation.summarize([])
        for key in ("top1_accuracy", "top3_recall", "abstention_accuracy", "noise_rate"):
            self.assertIsNone(metrics[key])
        metrics = evaluation.summarize([evaluation.score_case(case("negative", []), [])])
        self.assertEqual(metrics["abstention_accuracy"], 1)
        self.assertIsNone(metrics["top1_accuracy"])
        self.assertIsNone(metrics["noise_rate"])


class EvaluationDatasetTests(unittest.TestCase):
    def test_coverage_and_fixture_identities(self):
        cases, templates, finished_path, fingerprints = evaluation.load_dataset()
        self.assertEqual({c["category"] for c in cases}, evaluation.CATEGORIES)
        self.assertEqual({c["target"] for c in cases}, {"templates", "finished"})
        self.assertEqual(len(templates), 40)
        self.assertEqual(len(fingerprints), 3)
        self.assertNotEqual(finished_path, evaluation.ROOT / "data/meme_instances.json")
        self.assertTrue(all(c["rationale"] for c in cases))

    def test_bad_judgments_fail_before_search(self):
        original = json.loads(evaluation.DATASET.read_text(encoding="utf-8"))
        original["templates"] = str(evaluation.ROOT / "data/memes.json")
        original["finished_index"] = str(evaluation.ROOT / "tests/fixtures/search_eval_memes.json")
        mutations = [
            lambda d: d.update(version=2),
            lambda d: d.update(cases=[]),
            lambda d: d["cases"].append(deepcopy(d["cases"][0])),
            lambda d: d["cases"][0].update(relevant_ids=["nonexistent"]),
            lambda d: d["cases"][0].update(relevant_ids=["food"]),
            lambda d: d["cases"][0].update(abstain=True),
            lambda d: d["cases"][0].update(category="unknown"),
            lambda d: d["cases"][0].update(target="unknown"),
            lambda d: d["cases"][0].update(query="  "),
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "eval.json"
            for mutate in mutations:
                data = deepcopy(original)
                mutate(data)
                path.write_text(json.dumps(data), encoding="utf-8")
                with self.subTest(data=data["cases"][:1]), self.assertRaises(ValueError):
                    evaluation.load_dataset(path)

    def test_repeated_evaluation_is_offline_and_read_only(self):
        paths = [evaluation.DATASET, evaluation.ROOT / "data/memes.json",
                 evaluation.ROOT / "data/meme_instances.json",
                 evaluation.ROOT / "tests/fixtures/search_eval_memes.json"]
        before = [p.read_bytes() for p in paths]
        with ExitStack() as stack:
            guards = [stack.enter_context(patch(target, side_effect=AssertionError(target)))
                      for target in ("socket.socket.connect", "socket.create_connection", "socket.getaddrinfo",
                                     "utils.semantic.get_embedding_model", "utils.semantic.semantic_scores",
                                     "utils.search.semantic_fallback",
                                     "utils.external_index.search_external_templates")]
            first = evaluation.evaluate()
            second = evaluation.evaluate()
            for guard in guards:
                guard.assert_not_called()
        self.assertEqual(first, second)
        self.assertEqual(before, [p.read_bytes() for p in paths])
        self.assertEqual(first["overall"]["total"], len(first["cases"]))
        self.assertEqual(first["overall"]["failed"], len(first["failures"]))
        self.assertEqual(sum(v["total"] for v in first["by_category"].values()), len(first["cases"]))
        self.assertEqual(sum(v["total"] for v in first["by_target"].values()), len(first["cases"]))

    def test_cli_json_failure_details_and_exit_status(self):
        failed = evaluation.score_case(case("missing", ["a"]), [])
        report = {"profile": "test", "sha256": {}, "overall": evaluation.summarize([failed]),
                  "by_category": {"ambiguous": evaluation.summarize([failed])},
                  "by_target": {}, "failures": [failed], "cases": [failed]}
        with patch.object(evaluation, "evaluate", return_value=report):
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(evaluation.main(["--json"]), 0)
            self.assertEqual(json.loads(out.getvalue()), report)
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(evaluation.main(["--fail-on-failure"]), 1)
            self.assertIn("missing", out.getvalue())
            self.assertIn("expected=['a']", out.getvalue())
            self.assertIn("returned=[]", out.getvalue())
            self.assertIn("Top-3 recall", out.getvalue())


if __name__ == "__main__":
    unittest.main()
