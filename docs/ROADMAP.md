# Meme Finder — Development Roadmap

Last updated: 3 October 2026

This document defines the agreed development order for Meme Finder.

Do not skip ahead to later capability tracks unless this roadmap is deliberately
updated first.

## Priority 1 — Remove Gemini dependency

Status: COMPLETE

Goal:
Remove the unreliable external Gemini dependency while preserving useful OCR,
upload, search, identification, and creator infrastructure.

Completed:
- Removed active Gemini explanation dependency.
- Removed GEMINI_API_KEY requirement from the core product.
- Preserved local OCR.
- Preserved local template identification.
- Preserved search infrastructure.
- Preserved creator/editor functionality.
- External AI is no longer required for the core application.

---

## Priority 2 — Local Meme Explainer foundation

Status: IN PROGRESS — V1.1 VALIDATED / V2.1 PARTIAL

Branch: `feature/local-meme-explainer`

Goal: build a reliable local explanation foundation. The full chatbot remains
a separate later product-design discussion.

Completed work includes the deterministic local engine, corrected-caption-first
evidence, OCR fallback, optional template context, basic question intents,
related suggestions, and finished-meme supporting-evidence integration.
No external explanation API is required. Explanation depth remains limited
when caption and reliable template evidence are insufficient.

### V1.1 — OCR caption selection

A conservative effective-caption layer excludes numeric-only OCR lines while
preserving numbers inside meaningful text. Complete raw OCR remains available
for display/debugging, and user corrections still take precedence. The effective
caption is used by the local explainer and finished-meme retrieval.

Real manual example:

```text
Raw OCR:
38
ME PLANTING SEEDS OF DOUBT
50

Effective caption:
ME PLANTING SEEDS OF DOUBT
```

### V2.1 — template-reference recovery (partial)

Home previously showed 0/41 references because the cached index fingerprint
matched the previous 40 curated templates, while Home supplied 41
curated+imported templates. The mismatch rejected the whole index.

A local fallback now reuses validated URL-keyed cached images and recomputes
hashes when the fingerprint is stale. It adds no downloads or cache writes and
does not reuse stale IDs or embeddings. Existing reliability rules and
thresholds remain unchanged.

Home now has 38/41 usable references. A cached Distracted Boyfriend reference
returns `likely` through `identify()` and resolves through `reliable_template()`
when checked directly. Home still downgrades matches because coverage is
incomplete; V2 is not complete.

Missing references:

- Success Kid
- First World Problems
- Wasting Potential

Next priority: **V2.2** — restore these three references, reach full reference
coverage, and manually verify known-template recognition in the real app.

### Validated checkpoint — 3 October 2026

- Full regression: `.\.venv\Scripts\python.exe -B -m pytest -p no:cacheprovider -q`
  — 588 tests passed, 1,429 subtests passed.
- Search V4.8: `.\.venv\Scripts\python.exe -B -m utils.search_eval --fail-on-failure`
  — 34/34 passed; Top-1 100%, Top-3 recall 100%, abstention 100%, Noise@3 0%.
- `git diff --check`: clean.

---

## Priority 3 — Search Engine V4

Status: COMPLETE

Goal:
Move Meme Finder from primarily template-name search toward searching both
templates and real/finished memes by name, caption, description, meaning,
situation, and related context.

### V4.1 — Finished-meme index foundation

Status: COMPLETE

Added:
- Separate finished-meme data model.
- Provider-independent record normalization.
- Versioned finished-meme index.
- Provenance and metadata handling.

### V4.2 — Finished-meme retrieval and ranking

Status: COMPLETE

Search uses:
- caption
- topics
- situations
- optional template context
- source confidence

Includes weak-match rejection and deterministic ranking.

### V4.3 — Combined search

Status: COMPLETE

One query searches:

query
├── Finished Memes
└── Templates

Results remain separate groups.

### V4.4 — Search result actions

Status: COMPLETE

Finished memes:
- Download

Templates:
- Download
- Create Meme

### V4.5 — Finished-meme ingestion architecture

Status: COMPLETE

Pipeline:

source/provider
↓
normalize
↓
validate
↓
quality gate
↓
deduplicate
↓
persist finished-meme index

Includes:
- deterministic IDs
- provenance
- duplicate handling
- atomic writes
- locking
- index limits

### V4.6 — Controlled real-source ingestion

Status: COMPLETE

Current finished-meme adapter:
- GenMyMeme

Includes:
- robots.txt checks
- bounded requests
- quality filtering
- caption spam filtering
- malformed-record isolation
- strong-language metadata
- no automatic image crawling

### V4.7 — Query-driven/live discovery

Status: COMPLETE

When local indexes are insufficient, explicit live discovery can search approved
sources under strict crawl budgets.

Live discovery:
- is explicit
- is bounded
- does not silently persist results
- does not bypass source approval
- does not replace the local indexes

### V4.8 — Search benchmark and quality evaluation

Status: COMPLETE

Goal:
Prove Search V4 quality with a reproducible offline benchmark.

Evaluation dataset should include:

- exact template names
- aliases
- descriptions
- situations
- finished-meme captions
- typo queries
- Hinglish-lite queries
- ambiguous queries
- irrelevant/nonsense queries

Measure:

- Top-1 accuracy
- Top-3 recall
- irrelevant-result / noise rate
- correct abstention

The benchmark must not depend on live network results.

Post-merge checkpoint (2 October 2026, PR #27 merged to main): the frozen offline benchmark passes
34/34, with Top-1 accuracy, Top-3 recall and abstention accuracy all 100%, and
Noise@3 0%. The final full pytest suite passed: 555 tests, 1,396 subtests.
Search V4 is complete. These measurements cover the curated lexical/finished
fixture profile; broader hybrid-search quality remains outside this benchmark.
The current priority is Local Meme Explainer V2.2 reference coverage recovery.

---

## Priority 4 — Documentation and handoff

Status: IN PROGRESS

Goal:
Make the repository understandable without relying on ChatGPT conversation history.

Required documentation:

- `docs/PROJECT_STATUS.md`
- `docs/ROADMAP.md`
- `docs/search_engine.md`
- `docs/explainer.md`
- `README.md`

Documentation should explain:

- template search architecture
- finished-meme architecture
- provider architecture
- ranking pipeline
- ingestion
- deduplication
- live discovery
- explainer architecture
- schemas
- tests
- known limitations
- how to add providers
- how to run evaluation

---

## Later capability tracks

These remain valid future Meme Finder features, but they are not current work.

### Creator 2.0

Planned improvements:
- text positioning
- resizing
- multiple text layers
- crop/zoom
- undo/redo
- cleaner export
- better search-to-creator flow

### GIF + Sticker Finder

Status: NOT STARTED

Goal:
Search GIFs and stickers using the same retrieval philosophy as Meme Finder.

### Video Finder

Status: NOT STARTED

Goal:
Search reaction clips and video memes.

### GIF + Sticker Creator

Status: LONG-TERM

Goal:
Create/remix GIFs and stickers from templates/images.

### Video Creator

Status: LONG-TERM

Goal:
Caption, trim, and remix video memes.

---

## Full chatbot / Meme Explainer product

Status: FUTURE DESIGN DISCUSSION

This is intentionally separate from the Local Meme Explainer foundation.

Do not assume that finishing Priority 2 means building a full chatbot.

Before implementation, define:
- what the chatbot should understand;
- what information it may use;
- how conversation memory should work;
- how it should use real meme examples;
- what it should do for unknown memes;
- when it must abstain;
- whether any local model should be optional.

---

## Agreed development order

1. Remove Gemini dependency — COMPLETE
2. Build Local Meme Explainer foundation — IN PROGRESS
3. Finish Search Engine V4 — COMPLETE
   - V4.1 COMPLETE
   - V4.2 COMPLETE
   - V4.3 COMPLETE
   - V4.4 COMPLETE
   - V4.5 COMPLETE
   - V4.6 COMPLETE
   - V4.7 COMPLETE
   - V4.8 COMPLETE
4. Local Meme Explainer V2.2: full reference coverage and real-app recognition verification — NEXT
5. Finalize documentation / handoff
6. Creator 2.0
7. GIF + Sticker Finder
8. Video Finder
9. GIF + Sticker Creator
10. Video Creator

The full chatbot is scheduled separately after its design is discussed.
