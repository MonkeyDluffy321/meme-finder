"""Offline provider adapters. No search APIs or network calls."""

from utils.web_search import MEMEGEN_NAMES


def memegen_records(rows):
    """Adapt a saved Memegen bulk /templates/ export, not query responses."""
    for row in rows:
        if not isinstance(row, dict):
            yield row
            continue
        slug = row.get("id")
        if not isinstance(slug, str):
            yield None
            continue
        aliases = row.get("aliases", [])
        if not isinstance(aliases, list):
            yield None
            continue
        yield {"name": row.get("name"), "aliases": [*aliases, slug,
               slug.replace("-", " ").replace("_", " "), *MEMEGEN_NAMES.get(slug, ())],
               "provider": "memegen", "template_id": slug,
               "image_url": row.get("blank"), "source_page": row.get("source") or row.get("_self")}


def json_records(rows):
    """Import records already using the external-index schema."""
    yield from rows


PROVIDERS = {"memegen": memegen_records, "json": json_records,
             "memegen-repository": json_records}
