"""Reproducible lexical Search V4 baseline: python -m utils.search_eval."""

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path

from utils.meme_index import load_index
from utils.meme_search import search_finished_memes
from utils.search import search_memes


ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "tests/search_eval.json"
CATEGORIES = {
    "exact_names", "aliases", "descriptions", "situations", "finished_captions",
    "typos", "hinglish_lite", "ambiguous", "nonsense",
}


def load_dataset(path=DATASET):
    path = Path(path).resolve()
    dataset = json.loads(path.read_text(encoding="utf-8"))
    if type(dataset.get("version")) is not int or dataset["version"] != 1:
        raise ValueError("Unsupported evaluation dataset version")
    templates_path = (path.parent / dataset["templates"]).resolve()
    finished_path = (path.parent / dataset["finished_index"]).resolve()
    templates = json.loads(templates_path.read_text(encoding="utf-8"))
    finished = load_index(finished_path)
    raw_finished = json.loads(finished_path.read_text(encoding="utf-8"))
    if len(finished) != len(raw_finished["records"]):
        raise ValueError("Finished fixture contains invalid or collapsed records")
    pools = {"templates": [r["id"] for r in templates],
             "finished": [r["meme_id"] for r in finished]}
    for target, ids in pools.items():
        if not ids or len(ids) != len(set(ids)):
            raise ValueError(f"Empty or duplicate identities in {target} corpus")
    cases = dataset["cases"]
    if not cases:
        raise ValueError("Empty evaluation dataset")
    seen = set()
    for case in cases:
        identity = case["id"]
        if not isinstance(identity, str) or not identity or identity in seen:
            raise ValueError("Invalid or duplicate case ID")
        seen.add(identity)
        if case["category"] not in CATEGORIES or case["target"] not in pools:
            raise ValueError(f"Unknown category/target: {identity}")
        if not isinstance(case["query"], str) or not case["query"].strip():
            raise ValueError(f"Expected nonblank query: {identity}")
        relevant = case["relevant_ids"]
        if (not isinstance(relevant, list) or any(not isinstance(i, str) for i in relevant)
                or len(relevant) != len(set(relevant))
                or not set(relevant) <= set(pools[case["target"]])):
            raise ValueError(f"Invalid expected record IDs: {identity}")
        if type(case["abstain"]) is not bool or case["abstain"] != (not relevant):
            raise ValueError(f"Abstention must agree with expected IDs: {identity}")
    fingerprints = {name: hashlib.sha256(p.read_bytes()).hexdigest()
                    for name, p in (("dataset", path), ("templates", templates_path),
                                    ("finished_index", finished_path))}
    return cases, templates, finished_path, fingerprints


def score_case(case, returned_ids):
    """Score a single explicitly judged result group at cutoff three."""
    if len(returned_ids) != len(set(returned_ids)):
        raise ValueError("Duplicate result identities")
    expected = set(case["relevant_ids"])
    top = returned_ids[:3]
    noise = sum(identity not in expected for identity in top)
    top1 = bool(top and top[0] in expected) if expected else None
    recall = len(set(top) & expected) / len(expected) if expected else None
    abstention = not returned_ids if case["abstain"] else None
    passed = abstention if case["abstain"] else top1 and recall == 1 and noise == 0
    return {**case, "returned_ids": returned_ids, "top1": top1, "recall3": recall,
            "abstention": abstention, "noise_count": noise, "returned_at_3": len(top),
            "passed": bool(passed)}


def summarize(rows):
    positives = [r for r in rows if not r["abstain"]]
    negatives = [r for r in rows if r["abstain"]]
    returned = sum(r["returned_at_3"] for r in rows)
    noise = sum(r["noise_count"] for r in rows)
    passed = sum(r["passed"] for r in rows)
    return {
        "total": len(rows), "passed": passed, "failed": len(rows) - passed,
        "positive_cases": len(positives), "abstention_cases": len(negatives),
        "top1_accuracy": sum(r["top1"] for r in positives) / len(positives) if positives else None,
        "top3_recall": sum(r["recall3"] for r in positives) / len(positives) if positives else None,
        "abstention_accuracy": sum(r["abstention"] for r in negatives) / len(negatives) if negatives else None,
        "noise_rate": noise / returned if returned else None,
        "noise_count": noise, "returned_at_3": returned,
    }


def evaluate(path=DATASET):
    cases, templates, finished_path, fingerprints = load_dataset(path)
    rows = []
    for case in cases:
        if case["target"] == "templates":
            results = search_memes(templates, case["query"], use_semantic=False, require_strong=True)
            ids = [r["id"] for r in results]
        else:
            results = search_finished_memes(case["query"], index_path=finished_path, limit=20)
            ids = [r["meme_id"] for r in results]
        rows.append(score_case(case, ids))
    categories = defaultdict(list)
    targets = defaultdict(list)
    for row in rows:
        categories[row["category"]].append(row)
        targets[row["target"]].append(row)
    return {"profile": "offline-lexical-curated-and-fixture-v1", "sha256": fingerprints,
            "overall": summarize(rows),
            "by_category": {k: summarize(v) for k, v in sorted(categories.items())},
            "by_target": {k: summarize(v) for k, v in sorted(targets.items())},
            "failures": [r for r in rows if not r["passed"]], "cases": rows}


def format_report(report):
    def percent(value):
        return "N/A" if value is None else f"{value:.2%}"

    def line(label, metrics):
        return (f"{label}: {metrics['total']} cases; {metrics['passed']} passed / {metrics['failed']} failed; "
                f"Top-1 {percent(metrics['top1_accuracy'])}; Top-3 recall {percent(metrics['top3_recall'])}; "
                f"abstention {percent(metrics['abstention_accuracy'])}; noise@3 {percent(metrics['noise_rate'])}")

    lines = [report["profile"], line("Overall", report["overall"])]
    for section in ("by_category", "by_target"):
        lines.extend(line(k, v) for k, v in report[section].items())
    lines.append("Failed queries:")
    for row in report["failures"]:
        lines.append(f"  {row['id']} [{row['target']}] {row['query']!r}: "
                     f"expected={row['relevant_ids']} abstain={row['abstain']}; "
                     f"returned={row['returned_ids']}; Top-1={row['top1']} "
                     f"recall@3={row['recall3']} noise@3={row['noise_count']}")
    if not report["failures"]:
        lines.append("  None")
    lines.append("Input SHA256: " + json.dumps(report["sha256"], sort_keys=True))
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DATASET)
    parser.add_argument("--json", action="store_true", help="Print full machine-readable report")
    parser.add_argument("--fail-on-failure", action="store_true", help="Exit 1 if any case fails its judgments")
    args = parser.parse_args(argv)
    report = evaluate(args.dataset)
    print(json.dumps(report, indent=2) if args.json else format_report(report))
    return int(args.fail_on_failure and report["overall"]["failed"] > 0)


if __name__ == "__main__":
    raise SystemExit(main())
