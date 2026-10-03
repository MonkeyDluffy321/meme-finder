# Meme Finder — Local Meme Explainer

Last updated: 3 October 2026

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

## Chatbot boundary

A full Meme Explainer chatbot is a separate future product-design phase.

Do not automatically add:

- multi-turn conversational memory;
- general-purpose chat;
- unrestricted visual reasoning;
- external LLM calls;
- local large-model dependencies;

until the chatbot design has been explicitly discussed and documented.

## Branch checkpoint

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

## Next explainer milestone

1. V2.2: restore Success Kid, First World Problems and Wasting Potential references.
2. Reach full reference coverage and manually verify known-template recognition in the real app.
3. Continue explainer-specific quality and abstention evaluation before expansion.
4. Keep full chatbot design as a separate later discussion.
