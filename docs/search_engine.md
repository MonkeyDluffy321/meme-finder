# Meme Finder search engine

## Architecture and pipeline

Phase 1 adds a separate external template metadata index. The existing 41 local
templates (base catalog plus approved imports) are not replaced or modified.

1. `app.py` runs existing V1 lexical/fuzzy/semantic search against the local catalog.
2. Only when that returns no results, a nonblank Home query searches the external
   index. A local match always wins, even if filters subsequently hide it.
3. If both tiers are empty, the existing explicit **Search web** action remains.
   Its session cache, query invalidation, source approval and bounded crawler are unchanged.
4. Existing category/emotion filters apply after retrieval. External records
   currently have no category/emotion annotations, so active filters exclude them.

External-index search is offline: no query is sent to a provider. Exact normalized
name/alias lookups use an in-memory map. Other queries reuse V1's lexical/fuzzy
ranker with semantics disabled for this name-only metadata. Case, phrase and
number normalization come from V1. A bounded cache reloads on file mtime/size
changes, and callers receive copies. Blank browsing remains local-only.

External records display **External template / provider / Not curated**, with
source links and no Save/Recently Viewed actions. Images use the existing safe
downloader (DNS/IP pinning, SSRF/NAT64 checks, redirect and size/time/content limits,
indexing headers) and image validator. Previews are cached in memory for five
minutes. They are not downloaded during index lookup; only visible cards load them.
Live-crawler previews still reuse already validated bytes, without refetching.

Permanent catalog promotion is still exclusively:

`crawler → review queue → human approval → permanent catalog`

Index import and search never enqueue, approve or ingest memes. The external
index is persisted metadata, not a curated catalog. Live web results remain
temporary and are never written into either index or catalog.

## Index schema

`data/external_templates.json` contains:

```json
{
  "version": 1,
  "records": [{
    "name": "Business Cat",
    "aliases": ["business-cat", "office cat"],
    "provider": "imgflip-page",
    "template_id": "61531",
    "image_url": "https://imgflip.com/s/meme/Business-Cat.jpg",
    "source_page": "https://imgflip.com/memetemplate/Business-Cat"
  }],
  "imports": []
}
```

Name, provider, template ID and image URL are required. Aliases default to an
empty list; source page may be null. Text fields/aliases are capped at 200
characters, aliases at 32, URLs at 2,048 characters. The file is capped at 8 MiB
and 10,000 records. Import provenance retains the last 20 import summaries.

Malformed rows are skipped; broken/missing/unsupported/oversized index files
yield no external results. URL validation rejects unsupported schemes,
credentials, local hostnames and non-public literal IPs without doing DNS during
search. Safe preview downloads validate DNS and every redirect at request time.
Unknown fields are discarded, including injected local-file paths or UI flags.
In-memory results receive `external_result=true` and a provider-namespaced hashed ID.

Duplicate provider/template IDs and normalized image URLs collapse to one result;
alternate names/aliases are retained where space permits. Different images with
the same name are not automatically assumed identical.

## Providers and imports

The initial snapshot uses the official [Memegen bulk template export](https://api.memegen.link/templates/),
documented in its [source repository](https://github.com/jacebrowning/memegen).
This is an explicit metadata import, not a live meme-search API. No search API
or new package was added. The export yielded 209 unique records on 2026-09-21.
Business Cat was absent, so a separate JSON source supplies its published name,
aliases, ID and blank image from the [public template page](https://imgflip.com/memetemplate/Business-Cat).
The initial combined index contains 210 templates.

Save an updated provider export locally, then run from the repository root:

```powershell
python -m utils.external_importer --provider memegen --input tmp/memegen_templates.json --source https://api.memegen.link/templates/
python -m utils.external_importer --provider json --input data/external_sources/additional_templates.json
```

`--index` selects a separate index path for development. The importer explicitly
rejects the permanent catalog and review paths. It adapts a batch, validates and
deduplicates it, upserts by provider/template ID, retains unrelated providers,
checks combined limits, then atomically replaces the external index. Empty or
wholly invalid input and failed writes leave the previous index untouched.
Run one importer at a time; concurrent import coordination is not implemented.

To add another provider:

1. Prefer a local JSON list of records matching the schema and the `json` adapter
   (the input is the records array, not the versioned index wrapper).
2. Otherwise add a generator in `utils/external_providers.py` mapping that export
   into records and register it in `PROVIDERS`. Use a stable provider namespace.
3. Include real source/blank-image URLs and provider IDs; do not guess identities
   or put hundreds of template definitions in Python.
4. Add deterministic malformed/duplicate/import tests and import the saved batch.
   Adapters do not fetch webpages, execute provider content or send search queries.

The existing small trusted Memegen slug mapping is reused for aliases. Web
candidate identity enrichment and crawler protections are unchanged.

## Important files

| File | Responsibility |
| --- | --- |
| `app.py` | Local → external → explicit live-web routing and external card guards |
| `utils/search.py`, `utils/semantic.py` | Existing V1 ranking |
| `utils/external_index.py` | Validation, deduplication, cached index loading and search |
| `utils/external_providers.py` | Memegen-export and generic-JSON adapters |
| `utils/external_importer.py` | Explicit bounded atomic import CLI |
| `data/external_templates.json` | Searchable external metadata snapshot and provenance |
| `data/external_sources/additional_templates.json` | Maintainable supplemental source records |
| `utils/images.py` | Safe external preview loading |
| `utils/web_search.py`, `utils/crawler.py` | Existing approved-source live fallback |
| `utils/catalog_indexer.py`, `utils/catalog_review.py` | Separate human-review promotion workflow |

## Completed features and tests

Completed: curated-first routing, offline external identity search, provider
imports, case-insensitive names/aliases, safe external cards, malformed-record
handling, duplicate suppression, and unchanged explicit live fallback.

Offline tests cover Business Cat, DOGE, Drake, Success Kid, aliases, local priority,
unknown-query fallback, missing/malformed files, URL validation, duplicate records,
cache invalidation, copy isolation, repeat imports, atomic-write failures,
protected catalog paths, and safe preview validation. Existing V1, crawler,
catalog and Streamlit regressions remain part of the full suite.

```powershell
python -m unittest discover -s tests -p 'test_external_index*.py' -q
python -m unittest discover -s tests -q
```

## Current limitations and next roadmap phases

Imports are manual snapshots; deleted upstream templates remain until explicitly
removed from the external index. Preview availability and upstream metadata are
not guaranteed. External templates have not been human-curated or assigned local
category/emotion tags. Cross-provider visual duplicates and moderation are not
solved by URL/ID deduplication. Lookup uses an exact-name map followed by a bounded
linear V1 scan; the JSON backend targets thousands, not millions, of records.

The live crawler still has its existing total budget of 2 pages/4 images, normally
split as 1 page/2 images per approved source. No crawler expansion was used here.

Only Phase 1 was specified in the repository/task. Subsequent fixed-roadmap phase
names and order have not been supplied. Follow-on capabilities to schedule are:
additional provider coverage and refresh/removal policy; relevance evaluation and
richer metadata; provenance/moderation and visual deduplication; and a larger
indexed storage backend if measured scale requires it. None are implemented by
this change, and none should bypass human approval for permanent catalog entry.
