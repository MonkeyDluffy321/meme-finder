"""Bounded explicit-seed crawling into the internal review queue only."""

import argparse
from itertools import islice
import json

from utils.catalog_review import ReviewQueue, ReviewError
from utils.crawler import crawl, normalize_url, MAX_PAGES, MAX_IMAGES_PER_RUN
from utils.importer import DATA_DIR, ImportError, _read_records


PAGE_LIMIT = 10
IMAGE_LIMIT = 100


def index_catalog(seed_urls, memes, *, max_pages=MAX_PAGES,
                  max_images=MAX_IMAGES_PER_RUN, queue=None, provider=None):
    """Examine at most max_pages seed inputs; never approve or ingest results."""
    for value, ceiling, name in ((max_pages, PAGE_LIMIT, "max_pages"),
                                 (max_images, IMAGE_LIMIT, "max_images")):
        if type(value) is not int or not 1 <= value <= ceiling:
            raise ValueError(f"{name} must be an integer between 1 and {ceiling}.")
    if isinstance(seed_urls, (str, bytes)):
        raise ValueError("seed_urls must be an iterable of webpage URLs.")
    seeds = []
    for seed in islice(seed_urls, max_pages):
        url = normalize_url(seed)
        if not url:
            raise ValueError("Seeds must be public HTTP/HTTPS webpage URLs.")
        if url not in seeds:
            seeds.append(url)
    queue = queue if queue is not None else ReviewQueue()
    report = crawl(seeds, memes, max_pages=max_pages, max_images=max_images, provider=provider)
    candidates = report["candidates"]
    added = queue.enqueue(candidates) if candidates else []
    return {"seeds_submitted": len(seeds), "pages_processed": report["pages_processed"],
            "candidates_discovered": len(candidates), "candidates_queued": len(added),
            "skipped": len(report["skipped"]) + len(candidates) - len(added),
            "errors": len(report["errors"])}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("urls", nargs="+")
    parser.add_argument("--max-pages", type=int, default=MAX_PAGES)
    parser.add_argument("--max-images", type=int, default=MAX_IMAGES_PER_RUN)
    args = parser.parse_args(argv)
    try:
        memes = _read_records(DATA_DIR / "memes.json") + _read_records(
            DATA_DIR / "imported_memes.json", optional=True)
        summary = index_catalog(args.urls, memes, max_pages=args.max_pages, max_images=args.max_images)
    except (ValueError, OSError, ImportError, ReviewError) as error:
        parser.exit(1, f"Indexing failed: {error}\n")
    print(json.dumps(summary))
    return 1 if summary["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
