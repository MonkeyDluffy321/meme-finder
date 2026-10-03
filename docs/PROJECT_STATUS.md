# Meme Finder — Project Status

Last updated: 3 October 2026

This file is the source of truth for the current development checkpoint.
Read this file before continuing Meme Finder development.

## Current branch

`feature/local-meme-explainer`

Search V4.8 is complete and was merged into `main` via PR #27. This checkpoint
records the validated Local Meme Explainer working tree; it does not record a
new commit, push or merge.

## Current priority

Priority 2 — Local Meme Explainer foundation.

Finished-meme supporting-evidence integration remains in place. V1.1 caption
selection is validated; V2.1 reference recovery is partial. Next priority is
V2.2: restore the three missing references, reach full coverage, and manually
verify known-template recognition in the real app.

Full chatbot design, creator, GIF, sticker and video work remain later tracks.
Search V4 work remains limited to actual regressions or deliberately scoped improvements.

## Roadmap progress

### Priority 1 — Remove Gemini dependency

Status: COMPLETE

- Active Gemini API dependency removed.
- GEMINI_API_KEY requirement removed from the active product.
- Useful OCR, upload, search, identification, and creator infrastructure preserved.
- External AI is not required for the current Meme Finder core.

### Priority 2 — Local Meme Explainer foundation

Status: IN PROGRESS — V1.1 VALIDATED / V2.1 PARTIAL

The deterministic local foundation uses user corrections before effective OCR
captions, optional reliable template metadata, basic question intents, and
finished-meme supporting evidence without an external explanation API.
Explanations remain conservative and can be shallow for arbitrary finished memes.

#### V1.1 — OCR caption selection

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

#### V2.1 — template-reference recovery (partial)

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

At that 2 October Search checkpoint, no explainer development or branch integration
had been performed. The current explainer checkpoint is recorded above.

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

Local Meme Explainer working tree — 3 October 2026:

- Full regression: `.\.venv\Scripts\python.exe -B -m pytest -p no:cacheprovider -q`
  — 588 tests passed, 1,429 subtests passed.
- Search V4.8: `.\.venv\Scripts\python.exe -B -m utils.search_eval --fail-on-failure`
  — 34/34 passed; Top-1 100%, Top-3 recall 100%, abstention 100%, Noise@3 0%.
- `git diff --check`: clean.

## Exact next task

1. V2.2: restore Success Kid, First World Problems and Wasting Potential references.
2. Reach full reference coverage and manually verify known-template recognition in the real app.
3. Continue explainer-specific quality and abstention evaluation before expansion.
4. Keep full chatbot design as a separate later discussion.

## Session-start rule

Before continuing development, read in this order:

1. `docs/PROJECT_STATUS.md`
2. `docs/ROADMAP.md`
3. the relevant architecture document
4. `README.md` when public-product context is needed
