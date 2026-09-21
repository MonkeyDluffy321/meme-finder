"""Explicit offline imports into the separate external template index."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from utils.external_index import (INDEX_PATH, MAX_INDEX_BYTES, MAX_RECORDS,
                                  clean_records, read_index)
from utils.external_providers import PROVIDERS
from utils.importer import DATA_DIR, _write_records


def import_templates(input_path, *, provider, index_path=INDEX_PATH, source=None):
    """Upsert provider IDs atomically. Search never invokes this function."""
    path = Path(index_path).resolve()
    protected = {DATA_DIR / name for name in ("memes.json", "imported_memes.json", "catalog_review.json")}
    if path in {item.resolve() for item in protected}:
        raise ValueError("External imports cannot target catalog/review files.")
    with Path(input_path).open("rb") as handle:
        raw = handle.read(MAX_INDEX_BYTES + 1)
    if len(raw) > MAX_INDEX_BYTES:
        raise ValueError("Provider export exceeds byte limit.")
    rows = json.loads(raw)
    if not isinstance(rows, list) or len(rows) > MAX_RECORDS:
        raise ValueError("Expected a bounded provider JSON list.")
    if provider not in PROVIDERS:
        raise ValueError("Unknown provider adapter.")
    incoming = clean_records(PROVIDERS[provider](rows))
    if not incoming:
        raise ValueError("No valid templates; existing index unchanged.")
    previous = read_index(path) if path.exists() else {"version": 1, "records": [], "imports": []}
    keys = {(row["provider"], row["template_id"]) for row in incoming}
    retained = [row for row in clean_records(previous["records"])
                if (row["provider"], row["template_id"]) not in keys]
    records = clean_records([*incoming, *retained])
    records.sort(key=lambda row: (row["provider"], row["template_id"]))
    if len(records) > MAX_RECORDS:
        raise ValueError("Combined index exceeds record limit.")
    history = previous.get("imports", [])
    if not isinstance(history, list):
        history = []
    summary = {"adapter": provider, "source": source or Path(input_path).name,
               "imported_at": datetime.now(timezone.utc).isoformat(),
               "input_records": len(rows), "accepted_records": len(incoming), "index_size": len(records)}
    data = {"version": 1, "records": records, "imports": [*history[-19:], summary]}
    if len(json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")) + 1 > MAX_INDEX_BYTES:
        raise ValueError("Combined index exceeds byte limit.")
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_records(path, data)
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", choices=PROVIDERS, required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--index", type=Path, default=INDEX_PATH)
    parser.add_argument("--source", help="Provenance label/URL only; never fetched.")
    args = parser.parse_args(argv)
    try:
        report = import_templates(args.input, provider=args.provider, index_path=args.index, source=args.source)
    except (OSError, ValueError) as error:
        parser.exit(1, f"External import failed: {error}\n")
    print(json.dumps(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
