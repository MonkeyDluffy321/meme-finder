"""Explicit preparation of public references; normal analysis reads local files only."""

from functools import lru_cache
from hashlib import sha256
import json
import math
from pathlib import Path
from threading import RLock
from urllib.request import HTTPRedirectHandler, Request, build_opener

from PIL import Image, ImageStat

from utils.uploads import MAX_BYTES, validate_upload

CACHE = Path(__file__).resolve().parents[1] / ".cache" / "v3"
LOCAL_IMAGES = Path(__file__).resolve().parents[1] / "data" / "imported_images"
MODEL = "Qdrant/clip-ViT-B-32-vision"
VERSION = 1
_LOCK = RLock()


def image_hash(image):
    small = image.convert("L").resize((17, 16), Image.Resampling.LANCZOS)
    pixels = list(small.get_flattened_data())
    return "".join("1" if pixels[y * 17 + x] > pixels[y * 17 + x + 1] else "0"
                   for y in range(16) for x in range(16))


def informative(image):
    return ImageStat.Stat(image.convert("L").resize((64, 64))).stddev[0] >= 8


def fingerprint(memes):
    payload = [(m["id"], m.get("image_url", ""), m.get("local_image", "")) for m in memes]
    return sha256(json.dumps([VERSION, MODEL, payload]).encode()).hexdigest()


@lru_cache(maxsize=1)
def _model(cache_path, local_only):
    from fastembed import ImageEmbedding
    return ImageEmbedding(MODEL, cache_dir=cache_path, threads=2,
                          providers=["CPUExecutionProvider"], local_files_only=local_only)


def embed_images(images, *, download=False, cache=CACHE):
    with _LOCK:
        model = _model(str(cache / "models"), not download)
        vectors = [list(map(float, v)) for v in model.embed(images, batch_size=4)]
    if len(vectors) != len(images) or any(
            len(v) != 512 or not all(math.isfinite(x) for x in v) or not any(v) for v in vectors):
        raise ValueError("Invalid image embeddings")
    return vectors


def read_index(memes, cache=CACHE):
    try:
        data = json.loads((cache / "index.json").read_text(encoding="utf-8"))
        if data["fingerprint"] != fingerprint(memes):
            return read_cached_references(memes, cache)
        ids = {m["id"] for m in memes}
        rows = data["rows"]
        if not isinstance(rows, list) or len({r["id"] for r in rows}) != len(rows):
            return []
        for row in rows:
            if row["id"] not in ids or len(row["hash"]) != 256 or set(row["hash"]) - {"0", "1"}:
                return []
            vector = row.get("embedding")
            if vector is not None and (len(vector) != 512 or
                    not all(isinstance(x, (int, float)) and math.isfinite(x) for x in vector)):
                return []
        indexed = {row["id"] for row in rows}
        rows.extend(read_cached_references([m for m in memes if m["id"] not in indexed], cache))
        return rows
    except FileNotFoundError:
        return read_cached_references(memes, cache)
    except (OSError, ValueError, KeyError, TypeError):
        return []


def reference_path(meme, cache=CACHE):
    if meme.get("local_image"):
        return _local_image_path(meme["local_image"])
    url = meme.get("image_url")
    return cache / (sha256(url.encode()).hexdigest() + ".png") if url else None


def matches_reference_pixels(image, meme):
    path = reference_path(meme)
    try:
        if path is None or path.stat().st_size > MAX_BYTES:
            return False
        reference = validate_upload(path.read_bytes()).image
        return image.size == reference.size and image.convert("RGB").tobytes() == reference.tobytes()
    except (OSError, ValueError):
        return False


def read_cached_references(memes, cache=CACHE):
    """Reuse validated URL-keyed images when collection-wide metadata is stale.

    Recompute hashes instead of trusting old ID associations or embeddings.
    Missing/invalid references stay missing; no downloads or writes occur.
    """
    rows = []
    seen = set()
    for meme in memes:
        if meme["id"] in seen:
            continue
        seen.add(meme["id"])
        path = reference_path(meme, cache)
        if path is None:
            continue
        try:
            if path.stat().st_size > MAX_BYTES:
                continue
            upload = validate_upload(path.read_bytes())
            if informative(upload.image):
                rows.append({"id": meme["id"], "hash": image_hash(upload.image)})
        except (OSError, ValueError):
            continue
    return rows


def _local_image_path(filename):
    """Resolve a basename strictly inside the imported image directory."""
    if not isinstance(filename, str) or not filename or Path(filename).name != filename or "/" in filename or "\\" in filename:
        return None
    path = LOCAL_IMAGES / filename
    try:
        if path.resolve().parent != LOCAL_IMAGES.resolve():
            return None
    except OSError:
        return None
    return path


def _allowed_reference_url(url):
    from urllib.parse import urlsplit
    try:
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.query or parsed.fragment or parsed.username or parsed.password:
            return False
        if parsed.hostname == "i.imgflip.com":
            return parsed.port in (None, 443) and parsed.path.startswith("/")
        return (parsed.hostname == "imgflip.com" and parsed.port in (None, 443) and
                parsed.path in {"/s/meme/Success-Kid.jpg", "/s/meme/First-World-Problems.jpg"})
    except (TypeError, ValueError):
        return False


class _ValidatedRedirectHandler(HTTPRedirectHandler):
    """Follow redirects only while every destination remains an allowed reference."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not _allowed_reference_url(newurl):
            return None
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def prepare_index(memes, *, use_embeddings=True, cache=CACHE):
    """Only explicit setup calls download references/models. Retry reuses good files."""
    cache.mkdir(parents=True, exist_ok=True)
    rows, images = [], []
    for meme in memes:
        url = meme.get("image_url", "")
        filename = meme.get("local_image")
        # Filenames derive from URLs rather than untrusted IDs or uploaded names.
        if filename:
            path = _local_image_path(filename)
            if path is None:
                continue
        elif url:
            path = cache / (sha256(url.encode()).hexdigest() + ".png")
        else:
            continue
        try:
            if filename:
                with path.open("rb") as handle:
                    upload = validate_upload(handle.read(MAX_BYTES + 1))
            else:
                try:
                    upload = validate_upload(path.read_bytes())
                except (OSError, ValueError):
                    if not _allowed_reference_url(url):
                        continue
                    opener = build_opener(_ValidatedRedirectHandler())
                    with opener.open(Request(url, headers={"User-Agent": "MemeFinder/3.0"}), timeout=5) as response:
                        upload = validate_upload(response.read(MAX_BYTES + 1))
                    path.write_bytes(upload.preview)
            if informative(upload.image):
                rows.append({"id": meme["id"], "hash": image_hash(upload.image)})
                images.append(upload.image)
        except Exception:
            continue
    embedded = False
    if use_embeddings and images:
        try:
            vectors = embed_images(images, download=True, cache=cache)
            for row, vector in zip(rows, vectors):
                row["embedding"] = vector
            embedded = True
        except Exception:
            pass
    data = {"fingerprint": fingerprint(memes), "rows": rows}
    # Serialize writers and replace atomically so readers never see partial JSON.
    with _LOCK:
        temporary = cache / "index.tmp"
        temporary.write_text(json.dumps(data), encoding="utf-8")
        temporary.replace(cache / "index.json")
    return len(rows), embedded


def load_collection(data_dir=None):
    """Load curated templates and append imports using the app's ID precedence."""
    if data_dir is None:
        data_dir = Path(__file__).resolve().parents[1] / "data"
    collection = json.loads((data_dir / "memes.json").read_text(encoding="utf-8"))
    imported_path = data_dir / "imported_memes.json"
    if imported_path.exists():
        imported = json.loads(imported_path.read_text(encoding="utf-8"))
        if isinstance(imported, list):
            existing_ids = {meme["id"] for meme in collection}
            collection.extend(meme for meme in imported if meme.get("id") not in existing_ids)
    return collection


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hash-only", action="store_true")
    args = parser.parse_args(argv)
    collection = load_collection()
    count, embedded = prepare_index(collection, use_embeddings=not args.hash_only)
    print(f"Prepared {count}/{len(collection)} references; embeddings: {embedded}")


if __name__ == "__main__":
    main()
