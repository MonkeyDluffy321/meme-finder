# Meme Finder — Project Status

Last updated: 23 September 2026

This file is the source of truth for the current development checkpoint.
Read this file before continuing Meme Finder development.

## Current branch

`feature/search-v4-evaluation`

Based on the latest clean `main`.

## Current priority

Priority 3 — Search Engine V4

Current milestone:

**V4.8 — Search quality benchmark and evaluation**

Do not start new chatbot, creator, GIF, sticker, or video work until this
checkpoint is completed or the roadmap is deliberately changed.

## Roadmap progress

### Priority 1 — Remove Gemini dependency

Status: COMPLETE

- Active Gemini API dependency removed.
- GEMINI_API_KEY requirement removed from the active product.
- Useful OCR, upload, search, identification, and creator infrastructure preserved.
- External AI is not required for the current Meme Finder core.

### Priority 2 — Local Meme Explainer foundation

Status: PAUSED CHECKPOINT

Branch:

`feature/local-meme-explainer`

Current state:

- Local deterministic explainer foundation exists.
- Uses corrected visible text before OCR text.
- Can use reliable template metadata when available.
- Supports basic question intents.
- Does not require Gemini or another external explanation API.
- Current V4 `main` was merged into the explainer branch.
- Full regression suite after integration:
  - 546 tests passed
  - 1366 subtests passed
- Manual testing confirmed that the current explainer is conservative and safe,
  but explanation quality is still shallow for arbitrary finished memes.
- Example limitation: a Two Buttons taco-vs-pizza meme was read correctly after
  OCR correction, but the explainer mostly repeated the caption because it could
  not reliably recover the visual/template meaning.

The updated explainer branch has been pushed to GitHub.

Do not continue full chatbot development yet.

After Search V4.8, return to this foundation and connect it to stronger V4
finished-meme/template evidence.

### Priority 3 — Search Engine V4

Status: CURRENT PRIORITY

- V4.1 — Finished-meme index foundation: COMPLETE
- V4.2 — Finished-meme retrieval and ranking: COMPLETE
- V4.3 — Combined finished-meme + template search: COMPLETE
- V4.4 — Search result actions: COMPLETE
- V4.5 — Finished-meme ingestion pipeline: COMPLETE
- V4.6 — Controlled real-source ingestion and quality filtering: COMPLETE
- V4.7 — Explicit query-driven/live web discovery: COMPLETE
- V4.8 — Search benchmark and measurable quality evaluation: NEXT

Search currently supports separate Finished Memes and Templates result groups.

## Important finished-meme data note

The committed application index:

`data/meme_instances.json`

currently contains zero records on `main`.

The finished-meme search architecture itself works.

During previous local testing, a populated local index successfully returned real
finished memes, including examples using Success Kid and a "2006 Honda Civic"
captioned meme.

Therefore:

- finished-meme search code is working;
- finished-meme ingestion is working;
- the committed reusable application index is currently empty;
- data population and evaluation must be treated separately from search-engine code.

Do not confuse an empty index with a broken finished-meme search engine.

## V4.8 goals

Create a deterministic evaluation dataset covering:

- exact template names
- aliases
- descriptive searches
- situations
- finished-meme caption searches
- typo queries
- Hinglish-lite queries
- ambiguous queries
- irrelevant/nonsense queries

Measure at minimum:

- Top-1 accuracy
- Top-3 recall
- noise / irrelevant-result rate
- correct abstention

The benchmark must be reproducible and must not depend on live network results.

## Documentation state

Current documentation structure:

- `docs/PROJECT_STATUS.md` — current checkpoint and next task
- `docs/ROADMAP.md` — agreed development order
- `docs/search_engine.md` — search architecture
- `docs/explainer.md` — local explainer architecture and limitations
- `README.md` — public project overview and usage

Documentation must be updated after every meaningful development checkpoint.

`PROJECT_STATUS.md` should be updated whenever:

- the active branch changes;
- a milestone is completed;
- work is intentionally paused;
- a major test checkpoint is reached;
- the exact next task changes.

README should not be used as a development diary.

## Latest verified test checkpoint

On `feature/local-meme-explainer` after merging current V4:

`546 passed, 1366 subtests passed`

## Exact next task

1. Establish and commit the project-status/roadmap documentation.
2. Update Search V4 documentation to reflect V4.1–V4.7.
3. Fix stale README V4 wording.
4. Implement V4.8 evaluation dataset and benchmark runner.
5. Run the benchmark and record measured results.
6. Only then decide whether Search V4 is formally complete.

## Session-start rule

Before continuing development, read in this order:

1. `docs/PROJECT_STATUS.md`
2. `docs/ROADMAP.md`
3. the relevant architecture document
4. `README.md` when public-product context is needed