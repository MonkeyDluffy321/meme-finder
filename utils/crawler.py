"""Explicit-seed catalog discovery. Returns review data; never writes files."""

from hashlib import sha256
from html.parser import HTMLParser
from pathlib import Path
import re
from time import sleep
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

from utils.importer import LIST_FIELDS, normalize_list
from utils.importer_analysis import suggest_metadata
from utils.importer_url import download_image, download_resource
from utils.template_index import image_hash, informative, read_index
from utils.uploads import MAX_BYTES, validate_upload


MAX_PAGES = 3
MAX_IMAGES_PER_PAGE = 10
MAX_IMAGES_PER_RUN = 20
MAX_HTML_BYTES = 1024 * 1024
MAX_ROBOTS_BYTES = 128 * 1024
REQUEST_TIMEOUT = 5
REQUEST_DELAY = 0.5
MIN_IMAGE_SIDE = 100
NEAR_DUPLICATE_BITS = 2
USER_AGENT = "MemeFinder"
LOCAL_IMAGES = Path(__file__).resolve().parents[1] / "data" / "imported_images"


def normalize_url(value, base=""):
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not value or any(ord(c) <= 32 or ord(c) == 127 for c in value) or "\\" in value:
        return None
    try:
        parsed = urlsplit(urljoin(base, value))
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username is not None:
            return None
        parsed.port  # Validate malformed ports before any request.
        return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path or "/", parsed.query, ""))
    except ValueError:
        return None


class ImagePage(HTMLParser):
    def __init__(self, page, limit):
        super().__init__(convert_charrefs=True)
        self.page, self.limit = page, limit
        self.urls = []
        self.blocked = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "meta" and (attrs.get("name") or "").lower() in {"robots", "memefinder"}:
            self.blocked |= bool(set(re.split(r"[\s,]+", (attrs.get("content") or "").lower()))
                                 & {"noindex", "noimageindex", "none"})
        if tag != "img" or len(self.urls) >= self.limit:
            return
        for key in ("width", "height"):
            dimension = re.fullmatch(r"(\d+)(?:px)?", attrs.get(key) or "")
            if dimension and int(dimension[1]) < MIN_IMAGE_SIDE:
                return
        url = normalize_url(attrs.get("src"), self.page)
        if not url:
            return
        label = " ".join([urlsplit(url).path, attrs.get("class") or "", attrs.get("alt") or ""])
        if re.search(r"(?:^|[\W_])(avatar|favicon|icon|logo|tracker|tracking|pixel)(?:[\W_]|$)", label, re.I):
            return
        if url not in self.urls:
            self.urls.append(url)


def extract_images(html, page, limit=MAX_IMAGES_PER_PAGE):
    parser = ImagePage(page, limit)
    parser.feed(html)
    return [] if parser.blocked else parser.urls


def catalog_hashes(memes, *, image_dir=None):
    """Read existing hashes and bounded local images, never prepare/download references."""
    image_dir = Path(image_dir) if image_dir is not None else LOCAL_IMAGES
    hashes = [(row["hash"], row["id"]) for row in read_index(memes)]
    exact = {}
    for meme in memes:
        filename = meme.get("local_image")
        if not isinstance(filename, str) or not filename or "/" in filename or "\\" in filename:
            continue
        path = image_dir / filename
        if path.resolve().parent != image_dir.resolve():
            continue
        try:
            with path.open("rb") as handle:
                upload = validate_upload(handle.read(MAX_BYTES + 1))
            exact[sha256(upload.preview).hexdigest()] = meme["id"]
            if informative(upload.image):
                hashes.append((image_hash(upload.image), meme["id"]))
        except (OSError, ValueError):
            continue
    return hashes, exact


def crawl(seeds, memes, *, provider=None, max_pages=MAX_PAGES,
          images_per_page=MAX_IMAGES_PER_PAGE, max_images=MAX_IMAGES_PER_RUN,
          delay=REQUEST_DELAY, include_preview=False, max_robot_delay=None):
    """Return candidates/skipped/errors; caller owns review and later persistence.

    Only robots.txt and explicit pages/images are fetched. Robots failures deny
    access, including missing robots.txt. Pass a configured provider for headless use.
    """
    if min(max_pages, images_per_page, max_images) < 1 or delay < 0:
        raise ValueError("Crawler limits must be positive and delay nonnegative.")
    if max_robot_delay is not None and max_robot_delay < delay:
        raise ValueError("Robot delay budget must be at least the request delay.")
    report = {"candidates": [], "skipped": [], "errors": []}
    hashes, exact = catalog_hashes(memes)
    robots, pages, seen_images = {}, set(), set()

    def allowed(url):
        parsed = urlsplit(url)
        origin = urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))
        if origin not in robots:
            sleep(delay)
            data = download_resource(origin + "/robots.txt", content_types=("text/plain",),
                                     max_bytes=MAX_ROBOTS_BYTES, timeout=REQUEST_TIMEOUT)
            rules = RobotFileParser()
            rules.parse(data.decode("utf-8", errors="replace").splitlines())
            robots[origin] = rules
        rules = robots[origin]
        if not rules.can_fetch(USER_AGENT, url):
            return False
        rate = rules.request_rate(USER_AGENT)
        wait = max(delay, rules.crawl_delay(USER_AGENT) or 0,
                   rate.seconds / rate.requests if rate and rate.requests else 0)
        # Interactive callers skip slow sites rather than violate robots delays.
        if max_robot_delay is not None and wait > max_robot_delay:
            return False
        sleep(wait)
        return True

    for seed in seeds:
        if len(pages) >= max_pages or len(seen_images) >= max_images:
            break
        page = normalize_url(seed)
        if not page:
            report["errors"].append({"url": seed, "reason": "Unsupported seed URL"})
            continue
        if page in pages:
            continue
        pages.add(page)
        try:
            if not allowed(page):
                report["skipped"].append({"url": page, "reason": "robots.txt disallows access"})
                continue
            html = download_resource(page, content_types=("text/html", "application/xhtml+xml"),
                                     max_bytes=MAX_HTML_BYTES, timeout=REQUEST_TIMEOUT,
                                     respect_indexing=True)
            urls = extract_images(html.decode("utf-8", errors="replace"), page, images_per_page)
        except Exception as error:
            report["errors"].append({"url": page, "reason": str(error)})
            continue
        for url in urls:
            if len(seen_images) >= max_images:
                break
            if url in seen_images:
                continue
            seen_images.add(url)
            try:
                if not allowed(url):
                    report["skipped"].append({"url": url, "reason": "robots.txt disallows access"})
                    continue
                upload = validate_upload(download_image(url, respect_indexing=True))
                if min(upload.image.size) < MIN_IMAGE_SIDE:
                    report["skipped"].append({"url": url, "reason": "Image too small"})
                    continue
                digest = sha256(upload.preview).hexdigest()
                fingerprint = image_hash(upload.image)
                duplicate = exact.get(digest)
                if not duplicate and informative(upload.image):
                    duplicate = next((identity for other, identity in hashes
                                      if sum(a != b for a, b in zip(fingerprint, other)) <= NEAR_DUPLICATE_BITS), None)
                if duplicate:
                    report["skipped"].append({"url": url, "duplicate_status": "duplicate",
                                              "duplicate_of": duplicate})
                    continue
                metadata, notice = suggest_metadata(upload.preview, memes, provider=provider)
                candidate = {field: ",".join(metadata.get(field, [])) for field in LIST_FIELDS}
                candidate = {field: normalize_list(value) for field, value in candidate.items()}
                candidate.update({"id": "candidate-" + digest[:20],
                                  "name": metadata.get("name") or "Untitled meme " + digest[:8],
                                  "meaning": metadata.get("meaning") or "",
                                  "description": metadata.get("meaning") or "",
                                  "source_page": page, "source_image_url": url,
                                  "duplicate_status": "not_detected", "analysis_notice": notice,
                                  "content_sha256": digest, "image_hash": fingerprint})
                if include_preview:
                    candidate["_web_preview"] = upload.preview
                report["candidates"].append(candidate)
                exact[digest] = candidate["id"]
                if informative(upload.image):
                    hashes.append((fingerprint, candidate["id"]))
            except Exception as error:
                report["errors"].append({"url": url, "reason": str(error)})
    report["pages_processed"] = len(pages)
    return report
