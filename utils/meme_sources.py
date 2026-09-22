"""Explicit, bounded real-source imports into the V4.5 finished-meme pipeline."""

import argparse
import json
from pathlib import Path
import re
from time import sleep
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

from utils.catalog_sources import DEFAULT_CONFIG, validate_config
from utils.crawler import MAX_ROBOTS_BYTES, REQUEST_TIMEOUT, USER_AGENT
from utils.importer_url import download_resource
from utils.meme_index import INDEX_PATH
from utils.meme_ingestion import ingest_memes


ORIGIN = "https://genmymeme.com"
GALLERY = ORIGIN + "/api/v1/gallery"
MAX_BATCH = 50
MAX_RESPONSE_BYTES = 1024 * 1024
REQUEST_DELAY = 1
MAX_ROBOT_DELAY = 5


def _approved(config_path):
    config = json.loads(Path(config_path).read_text(encoding="utf-8"))
    validate_config(config)
    return any(source["approved"] and source["name"].casefold() == "genmymeme"
               and any(urlsplit(seed).netloc == "genmymeme.com" for seed in source["seeds"])
               for source in config["sources"])


def genmymeme_record(raw):
    """Map the public gallery's caption-layer JSON; never substitute blank templates."""
    if not isinstance(raw, dict):
        return None
    identity = raw.get("id")
    image = raw.get("image_url")
    if not isinstance(identity, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,100}", identity):
        return None
    if not isinstance(image, str):
        return None
    if image.startswith("/memes/"):
        image = ORIGIN + image
    parsed = urlsplit(image)
    if (parsed.scheme != "https" or parsed.netloc != "genmymeme.com"
            or not re.fullmatch(r"/memes/[a-zA-Z0-9_-]+\.(?:png|jpg|jpeg|webp)", parsed.path)
            or parsed.query or parsed.fragment):
        return None
    content = raw.get("text_content")
    if not isinstance(content, str) or len(content) > 32768:
        return None
    try:
        layers = json.loads(content)
    except ValueError:
        return None
    if (not isinstance(layers, list) or not 1 <= len(layers) <= 64
            or any(not isinstance(layer, dict) or not isinstance(layer.get("text"), str)
                   for layer in layers)):
        return None
    caption = "\n".join(layer["text"].strip() for layer in layers if layer["text"].strip())
    # Caption quality/length belongs to the shared ingestion gate, with reasons.
    return dict(provider="genmymeme", meme_id=identity, caption_text=caption,
                image_url=image, source_page=ORIGIN + "/m/" + identity,
                template_id=raw.get("template_id"), template_name=raw.get("template_name"),
                topics=raw.get("tags", []), situation=raw.get("description", raw.get("title", "")),
                language=raw.get("language", "und"), source_confidence="reported")


class GenMyMemeProvider:
    """One public gallery response, at most 50 candidates; no images or pagination."""

    name = "genmymeme"

    def __init__(self, limit=MAX_BATCH, *, config_path=DEFAULT_CONFIG):
        if type(limit) is not int or not 1 <= limit <= MAX_BATCH:
            raise ValueError("limit must be an integer from 1 to 50.")
        self.limit, self.config_path = limit, config_path
        self.error = None

    def records(self):
        self.error = None
        try:
            if not _approved(self.config_path):
                raise ValueError("GenMyMeme is not enabled in approved source configuration.")
            sleep(REQUEST_DELAY)
            content = download_resource(ORIGIN + "/robots.txt", content_types=("text/plain",),
                                        max_bytes=MAX_ROBOTS_BYTES, timeout=REQUEST_TIMEOUT)
            lines = content.decode("utf-8").splitlines()
            if not any(line.strip().lower().startswith("user-agent:") for line in lines):
                raise ValueError("Missing usable robots policy; source skipped.")
            rules = RobotFileParser()
            rules.parse(lines)
            if not rules.can_fetch(USER_AGENT, GALLERY):
                raise ValueError("robots.txt disallows the gallery; source skipped.")
            rate = rules.request_rate(USER_AGENT)
            delay = max(REQUEST_DELAY, rules.crawl_delay(USER_AGENT) or 0,
                        rate.seconds / rate.requests if rate and rate.requests else 0)
            if delay > MAX_ROBOT_DELAY:
                raise ValueError("robots.txt delay exceeds this runner's budget; source skipped.")
            sleep(delay)
            payload = json.loads(download_resource(GALLERY, content_types=("application/json",),
                                max_bytes=MAX_RESPONSE_BYTES, timeout=REQUEST_TIMEOUT, respect_indexing=True))
            if not isinstance(payload, dict) or not isinstance(payload.get("memes"), list):
                raise ValueError("Unexpected gallery response; source skipped.")
            for raw in payload["memes"][:self.limit]:
                try:
                    row = genmymeme_record(raw)
                    if row and not all(rules.can_fetch(USER_AGENT, row[key]) for key in ("image_url", "source_page")):
                        row = None
                except (TypeError, ValueError, RecursionError):
                    row = None
                yield row
        except Exception as error:
            self.error = str(error)
            raise


PROVIDERS = {"genmymeme": GenMyMemeProvider}


def run_sources(names=("genmymeme",), *, limit=MAX_BATCH, index_path=INDEX_PATH,
                config_path=DEFAULT_CONFIG):
    """Each adapter uses V4.5 unchanged; a failed source does not stop the next."""
    if not names or len(names) != len(set(names)) or any(name not in PROVIDERS for name in names):
        raise ValueError("Choose unique registered finished-meme providers.")
    if type(limit) is not int or not 1 <= limit <= MAX_BATCH:
        raise ValueError("limit must be an integer from 1 to 50 per provider.")
    reports = []
    for name in names:
        provider = PROVIDERS[name](limit=limit, config_path=config_path)
        report = ingest_memes(provider, index_path=index_path)
        report["provider"] = name
        if provider.error:
            report["source_error"] = provider.error
        reports.append(report)
    return {"sources": reports, "index_size": reports[-1]["index_size"]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", action="append", choices=PROVIDERS)
    parser.add_argument("--limit", type=int, default=MAX_BATCH, help="Candidate limit per provider (1-50)")
    parser.add_argument("--index", type=Path, default=INDEX_PATH)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args(argv)
    try:
        report = run_sources(args.provider or ["genmymeme"], limit=args.limit,
                             index_path=args.index, config_path=args.config)
    except (OSError, ValueError) as error:
        parser.exit(1, f"Finished-meme import failed: {error}\n")
    print(json.dumps(report, ensure_ascii=True))
    return 1 if any(row["errors"] for row in report["sources"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
