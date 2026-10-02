# Meme Finder — Local Meme Explainer

Last updated: 23 September 2026

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
local OCR
↓
user-corrected visible text if supplied
↓
optional template identification
↓
local template/search metadata
↓
deterministic explanation engine

## Evidence priority

The explainer should prefer evidence in this order:

1. User-corrected visible text
2. OCR-visible text
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

## Search V4 integration plan

After Search V4.8 is completed, the explainer foundation should gain stronger
retrieval context.

Planned flow:

Uploaded meme
↓
OCR / corrected visible text
↓
Search V4 finished-meme retrieval
+
template search / metadata
+
similar real meme examples
↓
structured explanation context
↓
local deterministic explanation engine

The goal is not to "train a chatbot" at this stage.

The goal is to provide better evidence to the existing local explainer.

## Real-meme grounding

Future explainer improvement should use real finished memes as retrieval evidence.

For example:

current meme
↓
retrieve similar indexed finished memes
↓
inspect captions, situations, topics, template metadata and provenance
↓
use those records as explanation context

This is retrieval-grounded explanation, not large-model training.

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

Current explainer development branch:

`feature/local-meme-explainer`

The latest checkpoint includes current Search V4 main merged into the branch.

Verified regression result:

- 546 tests passed
- 1366 subtests passed

The branch has been pushed to GitHub and is intentionally paused while Search V4.8
is completed.

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

Do not resume explainer feature development yet.

After Search V4.8:

1. connect the explainer to finished-meme retrieval;
2. combine real meme evidence with template metadata;
3. improve deterministic explanation quality;
4. create explainer-specific evaluation cases;
5. measure when it explains correctly versus when it should abstain.

Only after that should the separate chatbot design discussion begin.