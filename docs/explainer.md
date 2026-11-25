# Meme Finder — Local Meme Explainer

Last updated: 25 November 2026

## V2.2 checkpoint

Current branch: `feature/explainer-v2-2`. This section supersedes the historical
V2.1 partial-coverage, former-branch and next-milestone statements below.

Implemented behavior:

- The application and preparation CLI combine curated and imported catalogs,
  preserve curated IDs, tolerate a missing imported catalog and read UTF-8.
  Imported local images are indexed alongside curated references. Explicit
  preparation validates allowed reference download endpoints and redirects.
- Missing, partial or stale indexes recover available validated local references
  in memory without rewriting the active cache or retaining stale embeddings.
- Reliable visual matches supply trusted catalog meaning and usage. Decoded RGB
  pixel equality labels an already reliable winner as exact. Resized/recompressed
  variants can remain reliable under existing thresholds. Ambiguous matches and
  incomplete coverage retain conservative handling; OCR words do not prove identity.
- OCR caption selection uses bounding-box size, position, confidence and contextual
  evidence to separate probable captions from small peripheral interface labels
  and account names. Uncertain text is retained. Complete raw OCR remains available.
  The editable field receives the selected caption. Explicit manual corrections,
  including an empty correction, override it for explanation and related search.
- Streamlit refreshes saved analysis when catalog fingerprint, index timestamp or
  analysis revision changes. Automatic refresh preserves manual corrections.
  Explicitly clicking Read text locally resets the caption from new OCR.

Reported local verification reached 41/41 references, with 602 regression tests
and 1,435 subtests passed. Search V4 retained 34/34, Top-1 and Top-3 100%,
abstention 100%, Noise@3 0%. These are recorded session results, not a fresh run
for this documentation update. Prior Edge verification labeled Wasting My Potential's
original exact and a half-size quality-75 JPEG reliable, selecting two caption lines.

Manual testing explained Wasting My Potential correctly, but an NPC meme was not
explained despite successful OCR. The explainer is not a general-purpose meme
reasoning engine. Passing regressions and full reference coverage do not establish
general explanation quality. The historical browser downgrade was not conclusively
attributed to a particular session; stale-result reuse was reproduced and fixed.

## Planned hybrid architecture

Status: PLANNED. Keep existing offline OCR, identification and search as the
evidence foundation and fallback. Evaluate lightweight local AI through Ollama
behind a provider-independent interface. Optional cloud multimodal APIs require
explicit user consent before content is sent. Provider failure, unavailability or
declined consent should fall back gracefully to available local evidence. No
mandatory cloud dependency is planned.

The existing generic provider/result interface is a starting point. Ollama and
cloud integrations are not implemented by this checkpoint. Define evidence,
correction precedence, uncertainty, consent and failure contracts before integration.
Evaluate the NPC failure alongside recognized, unknown, captionless and ambiguous
inputs. Target hardware is 8 GB RAM, Intel i5-11300H and Iris Xe graphics; model
selection, resource use and performance remain unverified. Relocation to Disk D
is planned and has not been completed. Full chatbot memory remains separate work.

This document describes the current local Meme Explainer foundation.

The current explainer is not the final chatbot.

## Purpose

The Local Meme Explainer provides a conservative, offline-first explanation path
for uploaded or known memes without requiring Gemini or another external AI API.

Its current goal is:

- read visible meme text;
- use corrected text when the user fixes OCR;
- optionally use reliable template context;
- provide a grounded explanation when enough evidence exists;
- avoid inventing meme meanings when evidence is weak.

## Current pipeline

Uploaded meme
↓
image validation
↓
local OCR (complete raw text retained)
↓
effective caption selection / user-corrected visible text if supplied
↓
optional template identification
↓
local template metadata + finished-meme supporting evidence
↓
deterministic explanation engine

## Evidence priority

The explainer should prefer evidence in this order:

1. User-corrected visible text
2. Effective OCR caption
3. Reliable template identification
4. Local template metadata
5. Local search/related-meme evidence

User corrections must override OCR.

Template identification is supporting evidence, not proof.

## Current capabilities

The foundation currently supports:

- local OCR;
- corrected-caption-first explanation;
- optional template context;
- deterministic explanation rules;
- basic question intents;
- finished-meme retrieval as supporting evidence;
- local related-meme/template suggestions;
- abstention or limited explanations when evidence is insufficient;
- no external AI explanation API.

Supported question styles include basic forms such as:

- What does this meme mean?
- Why is this funny?
- When would I use this meme?
- What does the caption say?
- Show similar memes.

These are keyword/rule-based intents, not open-ended chatbot reasoning.

## Current limitations

The explainer does not currently provide general visual understanding.

It may fail when:

- the meme depends heavily on the visual template;
- OCR text alone does not reveal the joke;
- the template cannot be identified reliably;
- cultural context or meme history is required;
- sarcasm, slang, or irony cannot be inferred from available evidence.

The current system should prefer a limited answer over hallucinating.

## Manual test checkpoint

A Two Buttons meme was manually tested with:

- Taco
- Pizza
- "When you have to choose what to eat"

OCR initially merged some words.

After user correction, the explainer correctly used the corrected caption but
produced a shallow text-level explanation instead of reliably explaining the
Two Buttons convention.

This confirms:

- the local explanation pipeline works;
- correction precedence works;
- the current explanation depth is limited by available evidence.

## Search V4 supporting-evidence integration

Finished-meme supporting-evidence integration is already in place. Retrieval uses
the effective caption or user correction, alongside optional reliable template
metadata, to support the deterministic local explanation. Retrieved matches are
supporting evidence, not proof of identity or general visual understanding.

## Validated checkpoint — 3 October 2026

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

At the V2.1 checkpoint, Home had 38/41 usable references. A cached Distracted Boyfriend reference
returns `likely` through `identify()` and resolves through `reliable_template()`
when checked directly. Home still downgrades matches because coverage is
incomplete; V2 is not complete.

Missing references:

- Success Kid
- First World Problems
- Wasting Potential

Next priority: **V2.2** — restore these three references, reach full reference
coverage, and manually verify known-template recognition in the real app.

## Chatbot boundary

A full Meme Explainer chatbot is a separate future product-design phase.

Do not automatically add:

- multi-turn conversational memory;
- general-purpose chat;
- unrestricted visual reasoning;
- external LLM calls;
- local large-model dependencies;

until the chatbot design has been explicitly discussed and documented.

## Historical branch checkpoint — 3 October 2026

Current working tree: `feature/local-meme-explainer`.

- Full regression: `.\.venv\Scripts\python.exe -B -m pytest -p no:cacheprovider -q`
  — 588 tests passed, 1,429 subtests passed.
- Search V4.8: `.\.venv\Scripts\python.exe -B -m utils.search_eval --fail-on-failure`
  — 34/34 passed; Top-1 100%, Top-3 recall 100%, abstention 100%, Noise@3 0%.
- `git diff --check`: clean.

These results validate the current working tree; they do not establish full
reference coverage or completion of V2.

## Related files

Important implementation files include:

- `utils/local_explainer.py`
- `utils/intelligence.py`
- `utils/intelligence_ui.py`
- `utils/explanations.py`
- `utils/ocr.py`
- `utils/identification.py`
- `utils/template_index.py`
- `utils/vision.py`

Tests for the explainer and intelligence pipeline live under `tests/`.

## Historical next milestone — superseded by V2.2 checkpoint

1. V2.2: restore Success Kid, First World Problems and Wasting Potential references.
2. Reach full reference coverage and manually verify known-template recognition in the real app.
3. Continue explainer-specific quality and abstention evaluation before expansion.
4. Keep full chatbot design as a separate later discussion.
