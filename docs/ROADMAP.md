# Meme Finder — Development Roadmap

Last updated: 23 September 2026

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

Status: PAUSED / PARTLY COMPLETE

Branch:

`feature/local-meme-explainer`

Goal:
Build a reliable local explanation foundation.

This is NOT the final chatbot.

The foundation should use:

uploaded meme
↓
OCR / corrected visible text
↓
reliable template context when available
↓
local metadata / search evidence
↓
deterministic explanation
↓
abstain when evidence is insufficient

Current completed work:
- Local explanation engine.
- Corrected-caption-first evidence.
- OCR fallback.
- Optional template context.
- Basic question intents.
- Related meme/template suggestions.
- No external explanation API required.
- Current Search V4 main merged into branch.
- Integration regression suite:
  - 546 tests passed
  - 1366 subtests passed

Known limitation:
The current explainer is safe and conservative but often too shallow for arbitrary
finished memes because it lacks enough retrieved real-meme evidence.

Example:
A taco-vs-pizza Two Buttons meme had readable text, but the explainer mostly
repeated the caption instead of reliably explaining the visual/template joke.

Next work on Priority 2:
Resume only after Search V4.8.

Then connect the explainer to stronger Search V4 evidence:

OCR / corrected caption
↓
finished-meme retrieval
+
template metadata
+
similar real meme examples
↓
local explanation engine

Do not automatically turn this into a general-purpose chatbot.

The full chatbot/explainer product is a separate later design discussion.

---

## Priority 3 — Search Engine V4

Status: CURRENT PRIORITY

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

Status: NEXT

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

Search V4 is not formally closed until V4.8 is complete and results are reviewed.

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
2. Build Local Meme Explainer foundation — PARTLY COMPLETE / PAUSED
3. Finish Search Engine V4 — CURRENT
   - V4.1 COMPLETE
   - V4.2 COMPLETE
   - V4.3 COMPLETE
   - V4.4 COMPLETE
   - V4.5 COMPLETE
   - V4.6 COMPLETE
   - V4.7 COMPLETE
   - V4.8 NEXT
4. Return to Local Meme Explainer foundation
5. Finalize documentation / handoff
6. Creator 2.0
7. GIF + Sticker Finder
8. Video Finder
9. GIF + Sticker Creator
10. Video Creator

The full chatbot is scheduled separately after its design is discussed.