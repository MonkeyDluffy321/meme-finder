"""Run approved webpage sources through the catalog indexer; queue only."""

import argparse
import json
from pathlib import Path

from utils.catalog_indexer import index_catalog, PAGE_LIMIT, IMAGE_LIMIT
from utils.catalog_review import ReviewQueue
from utils.crawler import normalize_url
from utils.importer import DATA_DIR, ImportError, _read_records


DEFAULT_CONFIG = DATA_DIR / "catalog_sources.json"
DEFAULT_LIMITS = {"max_sources": 5, "max_pages": 3, "max_images": 20}
CEILINGS = {"max_sources": 10, "max_pages": PAGE_LIMIT, "max_images": IMAGE_LIMIT}
STATS = ("pages_processed", "candidates_discovered", "candidates_queued", "skipped", "errors")


def validate_config(config):
    if not isinstance(config, dict) or set(config) - {"limits", "sources"}:
        raise ValueError("Expected limits and sources configuration.")
    supplied = config.get("limits", {})
    if not isinstance(supplied, dict) or set(supplied) - set(DEFAULT_LIMITS):
        raise ValueError("Unknown source runner limits.")
    limits = {**DEFAULT_LIMITS, **supplied}
    for key, value in limits.items():
        if type(value) is not int or not 1 <= value <= CEILINGS[key]:
            raise ValueError(f"{key} must be an integer between 1 and {CEILINGS[key]}.")
    sources = config.get("sources")
    if not isinstance(sources, list) or len(sources) > limits["max_sources"]:
        raise ValueError("sources must be a list within max_sources.")
    names = set()
    for source in sources:
        if not isinstance(source, dict) or set(source) != {"name", "approved", "seeds"}:
            raise ValueError("Each source needs name, approved and seeds.")
        name, seeds = source["name"], source["seeds"]
        if not isinstance(name, str) or not name.strip() or name.strip() in names:
            raise ValueError("Source names must be nonempty and unique.")
        names.add(name.strip())
        if type(source["approved"]) is not bool:
            raise ValueError("approved must be a boolean.")
        if (not isinstance(seeds, list) or not 1 <= len(seeds) <= limits["max_pages"]
                or any(not normalize_url(seed) for seed in seeds)):
            raise ValueError("seeds must contain webpage URLs within max_pages.")
    return limits


def run_sources(config, memes, *, queue=None, provider=None):
    """Validate before crawling. Limits apply per source; source count bounds the run."""
    limits = validate_config(config)
    queue = queue if queue is not None else ReviewQueue()
    results, seen = [], set()
    for source in config["sources"]:
        stats = dict.fromkeys(STATS, 0)
        result = {"name": source["name"], **stats}
        results.append(result)
        if not source["approved"]:
            result["skipped"] = len(source["seeds"])
            continue
        seeds = []
        for seed in source["seeds"]:
            url = normalize_url(seed)
            if url in seen:
                result["skipped"] += 1
            else:
                seen.add(url)
                seeds.append(url)
        if not seeds:
            continue
        try:
            summary = index_catalog(seeds, memes, max_pages=limits["max_pages"],
                                    max_images=limits["max_images"], queue=queue, provider=provider)
            for key in STATS:
                result[key] += summary[key]
        except Exception as error:
            # Isolate source/queue failures without approving or retrying candidates.
            result["errors"] += 1
            result["error"] = str(error)
    return {"sources": results,
            "overall": {key: sum(row[key] for row in results) for key in STATS}}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args(argv)
    try:
        config = json.loads(args.config.read_text(encoding="utf-8"))
        validate_config(config)
        memes = _read_records(DATA_DIR / "memes.json") + _read_records(
            DATA_DIR / "imported_memes.json", optional=True)
        summary = run_sources(config, memes)
    except (ValueError, OSError, ImportError) as error:
        parser.exit(1, f"Source indexing failed: {error}\n")
    print(json.dumps(summary))
    return 1 if summary["overall"]["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
