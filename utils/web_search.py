"""Explicit, memory-only retrieval from configured approved webpage seeds."""

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

from utils.catalog_sources import DEFAULT_CONFIG, validate_config
from utils.crawler import crawl, normalize_url, REQUEST_DELAY
from utils.search import normalize_query, search_memes


MAX_SOURCES = 2
MAX_PAGES = 2
IMAGES_PER_PAGE = 2
MAX_IMAGES = 4
MAX_ROBOT_DELAY = 2


def search_web(memes, query, *, config_path=DEFAULT_CONFIG, provider=None):
    """Call only after explicit fallback action. Never enqueue, ingest or save.

    Budgets are global, not per source. Query text is used only for ranking;
    only configured seeds reach crawl. Failures abstain without affecting V1.
    """
    query = normalize_query(query).strip()
    if not query:
        return []
    try:
        config = json.loads(Path(config_path).read_text(encoding="utf-8"))
        limits = validate_config(config)
        approved = [source for source in config["sources"] if source["approved"]][:MAX_SOURCES]
        sources, seen_seeds = [], set()
        for source in approved:
            seeds = []
            for seed in source["seeds"]:
                url = normalize_url(seed)
                if url and url not in seen_seeds:
                    seen_seeds.add(url)
                    seeds.append(url)
            if seeds:
                sources.append(seeds)
        pages = min(MAX_PAGES, limits["max_pages"])
        images = min(MAX_IMAGES, limits["max_images"])
        sources = sources[:min(pages, images)]
        if not sources:
            return []
        discovered = []
        # Reserve shares before crawling; errors/unused slots never increase a
        # source's share. Remainders go to earlier configured sources.
        for index, seeds in enumerate(sources):
            page_budget = pages // len(sources) + (index < pages % len(sources))
            image_budget = images // len(sources) + (index < images % len(sources))
            seeds = seeds[:page_budget]
            try:
                report = crawl(seeds, memes, provider=provider, max_pages=page_budget,
                               images_per_page=IMAGES_PER_PAGE, max_images=image_budget,
                               delay=REQUEST_DELAY, include_preview=True,
                               max_robot_delay=MAX_ROBOT_DELAY)
                discovered.extend((seeds, candidate) for candidate in report["candidates"][:image_budget])
            except Exception:
                continue
        seen_urls = {normalize_url(meme.get("source_image_url") or meme.get("image_url"))
                     for meme in memes}
        seen_hashes = {meme.get("content_sha256") for meme in memes}
        candidates = []
        for seeds, candidate in discovered:
            url = normalize_url(candidate.get("source_image_url"))
            digest = candidate.get("content_sha256")
            if (not url or normalize_url(candidate.get("source_page")) not in seeds
                    or url in seen_urls or (digest and digest in seen_hashes)):
                continue
            seen_urls.add(url)
            seen_hashes.add(digest)
            result = deepcopy(candidate)
            result.update(web_result=True, id="web-" + sha256(url.encode()).hexdigest())
            result["image_url"] = result.get("image_url") or url
            result["name"] = result.get("name") or "Untitled web meme"
            result["meaning"] = result.get("meaning") or ""
            candidates.append(result)
        return search_memes(candidates, query) if candidates else []
    except Exception:
        return []
