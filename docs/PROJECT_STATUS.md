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

**V4.8 — Search quality benchmark and evaluation: infrastructure added; baseline measured**

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
- V4.8 — Search benchmark and measurable quality evaluation: IN PROGRESS

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

### First offline baseline — 23 September 2026

Added `tests/search_eval.json` (34 cases across all nine categories),
`tests/fixtures/search_eval_memes.json` (four isolated synthetic finished memes
from existing search tests), `utils/search_eval.py`, and evaluator correctness
tests in `tests/test_search_eval.py`.

Run `.\.venv\Scripts\python.exe -m utils.search_eval` from the repository root.
Use `--json` for the full report, including input fingerprints, or
`--fail-on-failure` to exit nonzero for failed judgments.

Profile: `offline-lexical-curated-and-fixture-v1`. It measures all 40 curated
templates and the isolated finished fixture through existing search APIs.
Semantic models, external-template fallback, live discovery and UI routing are
excluded. No ranking behavior, production data, dependencies or configuration
were changed. This baseline does not establish full hybrid-search quality.

| Metric | Baseline |
| --- | --- |
| Cases | 34: 30 passed, 4 failed |
| Positive / abstention cases | 26 / 8 |
| Top-1 accuracy | 88.46% (23/26) |
| Top-3 recall (mean per positive case) | 88.46% |
| Correct abstention | 100% (8/8) |
| Noise@3 | 3.85% (1 irrelevant / 26 returned slots) |
| Template cases passed | 20/23 |
| Finished-meme cases passed | 10/11 |

All exact-name, alias, description, finished-caption, typo, ambiguous and nonsense
cases passed. Situations passed 3/4; Hinglish-lite passed 0/3.

Failed judgments (retained without tuning):

- `can't decide what to eat`: expected finished ID `food`; returned `food`,
  `sleep`. The first result is correct, but the second is irrelevant.
- `do buttons mein choice`: expected template `two-buttons`; returned nothing.
- `sab jal raha hai but this is fine`: expected template `this-is-fine`;
  returned nothing.
- `harold dard wali smile`: expected template `hide-the-pain-harold`;
  returned nothing.

Positive cases require a relevant first result, complete recall@3, and zero
noise@3 to pass. Abstention cases require an empty result list. See
[search evaluation documentation](search_engine.md#offline-evaluation-v48)
for metric definitions, scope and reproducibility limitations. V4.8 is not
formally complete; the explainer foundation remains paused.

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

On `feature/search-v4-evaluation`, after adding the evaluator:

- Focused: `.\.venv\Scripts\python.exe -m pytest tests/test_search_eval.py -q`
  — 7 passed, 9 subtests passed.
- Full: `.\.venv\Scripts\python.exe -m pytest -q`
  — 536 passed, 1368 subtests passed (116.38 seconds).

These checks validate infrastructure and regressions; the four benchmark quality
failures above remain measured failures. The earlier explainer-branch result
(546 tests, 1366 subtests) belongs to its separate paused checkpoint.

## Exact next task

1. Review the four baseline failures and their relevance judgments, especially
   Hinglish recall and finished-meme situation noise.
2. Agree the next measured quality change and any additional evaluation coverage
   before tuning ranking; preserve this baseline for comparison.
3. Rerun the benchmark and regression suite after any approved follow-up changes.
4. Review results before declaring V4.8/Search V4 complete, then return to the
   paused Local Meme Explainer foundation. Full chatbot design remains separate.

## Session-start rule

Before continuing development, read in this order:

1. `docs/PROJECT_STATUS.md`
2. `docs/ROADMAP.md`
3. the relevant architecture document
4. `README.md` when public-product context is needed
