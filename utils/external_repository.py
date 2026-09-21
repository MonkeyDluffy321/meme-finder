"""Offline bulk adapter for the public tenequm/memegen-rs template repository."""

import os
from pathlib import Path
import re
import subprocess
from urllib.parse import quote

import yaml  # Already required by RapidOCR and huggingface_hub.

from utils.external_index import MAX_RECORDS, searchable_metadata


REPOSITORY = "https://github.com/tenequm/memegen-rs"


def repository_records(directory):
    """Read checked-out metadata only; never run repository code or fetch blobs."""
    root = Path(directory).resolve()
    environment = {**os.environ, "GIT_NO_LAZY_FETCH": "1"}

    def git(*args):
        try:
            return subprocess.run(["git", "-C", str(root), *args], check=True,
                                  capture_output=True, text=True, timeout=15,
                                  env=environment).stdout.strip()
        except (OSError, subprocess.SubprocessError) as error:
            raise ValueError("Cannot read local template repository.") from error

    revision = git("rev-parse", "HEAD")
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("Expected a pinned Git revision.")
    paths = git("ls-tree", "-r", "--name-only", "HEAD", "templates").splitlines()
    configs = [path for path in paths if re.fullmatch(r"templates/[a-z0-9_-]+/config.yml", path)]
    if len(configs) > MAX_RECORDS:
        raise ValueError("Repository exceeds template limit.")
    tracked = set(paths)
    rows = []
    for relative in configs:
        config = (root / relative).resolve()
        if not config.is_relative_to(root):
            continue
        slug = relative.split("/")[1]
        image = next((f"templates/{slug}/default.{ext}" for ext in ("png", "jpg", "jpeg", "webp", "gif")
                      if f"templates/{slug}/default.{ext}" in tracked), None)
        if not image:
            continue
        try:
            with config.open("rb") as handle:
                raw = handle.read(65537)
            if len(raw) > 65536:
                continue
            metadata = yaml.safe_load(raw)
        except (OSError, UnicodeError, yaml.YAMLError, RecursionError):
            continue
        if not isinstance(metadata, dict):
            continue
        aliases = metadata.get("aliases", [])
        if not isinstance(aliases, list):
            continue
        rows.append({"name": metadata.get("name"), "aliases": [*aliases, slug, slug.replace("-", " ")],
                     "provider": "memegen-repository", "template_id": slug,
                     "image_url": f"https://raw.githubusercontent.com/tenequm/memegen-rs/{revision}/{quote(image)}",
                     "source_page": metadata.get("source") or f"{REPOSITORY}/tree/{revision}/templates/{slug}",
                     **searchable_metadata(metadata)})
    return rows
