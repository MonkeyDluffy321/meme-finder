# Meme Finder — Project Status

Last updated: 2 October 2026

This file is the source of truth for the current development checkpoint.
Read this file before continuing Meme Finder development.

## Current branch

`docs/post-v4.8-checkpoint` (documentation only)

Search V4.8 was merged into `main` via PR #27. Locally synced `main` is the
current completed Search V4 checkpoint; this branch records the post-merge handoff.

## Current priority

Return to Priority 2 — Local Meme Explainer foundation

Current milestone:

**V4.8 COMPLETE — Search V4 is complete.**

Next work is connecting the Local Meme Explainer foundation to Search V4 evidence.
Full chatbot design, creator, GIF, sticker, and video work remain later tracks.
Future Search V4 work is limited to actual regressions or deliberately scoped
improvements; it is not the next development priority.

## Roadmap progress

### Priority 1 — Remove Gemini dependency

Status: COMPLETE

- Active Gemini API dependency removed.
- GEMINI_API_KEY requirement removed from the active product.
- Useful OCR, upload, search, identification, and creator infrastructure preserved.
- External AI is not required for the current Meme Finder core.

### Priority 2 — Local Meme Explainer foundation

Status: PAUSED CHECKPOINT — NEXT PRIORITY TO RESUME

Branch:

`feature/local-meme-explainer`

Current state:

- Local deterministic explainer foundation exists.
- Uses corrected visible text before OCR text.
- Can use reliable template metadata when available.
- Supports basic question intents.
- Does not require Gemini or another external explanation API.
- The then-current V4 `main` was merged into the explainer branch at its paused checkpoint.
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

Search V4.8 is complete; next return to this foundation and connect it to stronger V4
finished-meme/template evidence.

### Priority 3 — Search Engine V4

Status: COMPLETE

- V4.1 — Finished-meme index foundation: COMPLETE
- V4.2 — Finished-meme retrieval and ranking: COMPLETE
- V4.3 — Combined finished-meme + template search: COMPLETE
- V4.4 — Search result actions: COMPLETE
- V4.5 — Finished-meme ingestion pipeline: COMPLETE
- V4.6 — Controlled real-source ingestion and quality filtering: COMPLETE
- V4.7 — Explicit query-driven/live web discovery: COMPLETE
- V4.8 — Search benchmark and measurable quality evaluation: COMPLETE

Search currently supports separate Finished Memes and Templates result groups.

## Important finished-meme data note

The committed application index:

`data/meme_instances.json`

now contains 19 reviewed persistent finished-meme records on `main`.
The app uses this index, not a temporary preview file. Manual verification
confirmed finished searches for `2006 honda`, `change my mind`, and `movie night`.
Ordinary profanity is not blanket-blocked. The frozen offline benchmark continues
to use its separate controlled fixture; data population and evaluation are distinct.

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

Original failed judgments (all resolved at the completion checkpoint below):

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
for metric definitions, scope and reproducibility limitations.

### V4.8 post-merge completion checkpoint — 2 October 2026

Search V4 is complete and merged to `main` via PR #27. The frozen benchmark passes 34/34:

- Top-1 accuracy: 100% (26/26 positive cases).
- Top-3 recall: 100% (mean over 26 positive cases).
- Abstention accuracy: 100% (8/8 cases).
- Noise@3: 0% (0/28 returned slots).
- No remaining benchmark failures; all nine categories pass.

Changes add conservative query-only Hinglish-lite normalization, unique embedded
complete catalog-name/alias recovery with supported context and ambiguity/negation
guards, and suppression of weaker finished-meme subset matches behind a
full-coverage leader. Exact captions and equally supported alternatives survive.
The benchmark is unchanged; the persistent application index now has 19 reviewed
records. Benchmark results apply to the documented
offline lexical profile, not comprehensive production hybrid-search quality.

The next priority is returning to the Local Meme Explainer foundation; no
explainer development or branch integration has been performed at this checkpoint.

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

Final verified Search V4 checkpoint, now merged to `main`:

- Full: `.\.venv\Scripts\python.exe -m pytest -q`
  — 555 tests passed, 1,396 subtests passed.

These checks validate infrastructure and regressions; all four original benchmark
failures are resolved. The earlier explainer-branch result
(546 tests, 1366 subtests) belongs to its separate paused checkpoint.

## Exact next task

1. Return to the Local Meme Explainer foundation checkpoint on
   `feature/local-meme-explainer`, using completed Search V4 on `main` as the
   integration checkpoint when branch integration is authorized.
2. Connect finished-meme retrieval and template metadata to explanation context.
3. Add explainer-specific quality and abstention evaluation before expanding it.
4. Keep full chatbot design as a separate later discussion.

## Session-start rule

Before continuing development, read in this order:

1. `docs/PROJECT_STATUS.md`
2. `docs/ROADMAP.md`
3. the relevant architecture document
4. `README.md` when public-product context is needed
