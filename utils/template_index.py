"""Explicit preparation of public references; normal analysis reads local files only."""

from functools import lru_cache
from hashlib import sha256
import json
import math
from pathlib import Path
from threading import RLock
from urllib.request import Request, urlopen

from PIL import Image, ImageStat

from utils.uploads import MAX_BYTES, validate_upload

CACHE = Path(__file__).resolve().parents[1] / ".cache" / "v3"
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
    payload = [(m["id"], m["image_url"]) for m in memes]
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
            return []
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
        return rows
    except (OSError, ValueError, KeyError, TypeError):
        return []


def prepare_index(memes, *, use_embeddings=True, cache=CACHE):
    """Only explicit setup calls download references/models. Retry reuses good files."""
    cache.mkdir(parents=True, exist_ok=True)
    rows, images = [], []
    for meme in memes:
        url = meme["image_url"]
        # Filenames derive from URLs rather than untrusted IDs or uploaded names.
        path = cache / (sha256(url.encode()).hexdigest() + ".png")
        try:
            try:
                upload = validate_upload(path.read_bytes())
            except (OSError, ValueError):
                if not url.startswith("https://i.imgflip.com/"):
                    continue
                with urlopen(Request(url, headers={"User-Agent": "MemeFinder/3.0"}), timeout=5) as response:
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


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hash-only", action="store_true")
    args = parser.parse_args()
    collection = json.loads((Path(__file__).resolve().parents[1] / "data/memes.json").read_text())
    count, embedded = prepare_index(collection, use_embeddings=not args.hash_only)
    print(f"Prepared {count}/{len(collection)} references; embeddings: {embedded}")
