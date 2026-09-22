# Meme Finder

## Search Engine V4 foundation (V4.1–V4.2)

V4 is designed to search both **meme templates** and **recurring/known finished
memes**, not every meme ever posted online. V4.1 adds the finished-meme data
layer; V4.2 adds retrieval. Existing V3 template search and UI remain unchanged.

`data/meme_instances.json` is a separate versioned index, initially empty.
`utils/meme_index.py` validates and normalizes provider-independent records:
`meme_id`, `provider`, `caption_text`, derived `normalized_caption`, optional
`template_id`/`template_name`, `topics`, `situation`, `language`, `image_url`,
`source_page` and `source_confidence`. A known template is never required.
Provider adapters can implement `MemeProvider.records()` for approved sources;
there is no crawler or provider integration yet.

`utils.meme_search.search_finished_memes(query, index_path=..., limit=20)` returns
ranked finished records. Exact captions lead, followed by query-token coverage and
weighted captions, topics, situations and optional template context. Source confidence
breaks relevance ties; soft copies receive a small demotion but remain eligible.
Empty or insufficiently matching queries return no results. Ranking is deterministic,
local and lexical: it loads no semantic models, makes no network calls, and does not
infer paraphrases without shared words in the indexed metadata.

Local ingestion can compute image fingerprints from validated bytes. Exact image
or decoded-pixel copies collapse with source provenance and caption variants.
Identical URL/caption records also collapse. Matching perceptual hashes with the
same caption only flag possible copies, retaining both records; compressed/resized
variants are not aggressively removed. Different captions and meaningful variations
remain separate. Hashes and source-confidence claims require trusted ingestion;
URL syntax validation does not authorize downloading or approve a source.

Future query results can expose **Finished Memes**, then **Templates**, as separate
groups. Planned actions are Download for finished memes and Download/Create Meme
for templates. V4.1 implements none of these UI controls. Tests use small synthetic
records with placeholder URLs, not a production collection.

Meme Finder is a Python and Streamlit app for finding meme templates by
name, description, emotion, or situation. The current collection contains
**40 meme templates**, with searchable metadata and remote image previews.
Browse and search as a guest, or sign in to keep a personal meme library.

The external Gemini explainer was removed. A new local **Meme Explainer** is
planned separately. Local OCR, upload normalization, template identification,
metadata and related meme retrieval remain available. Search Engine V3,
accounts, libraries and the creator/editor retain their existing behavior.

## Local image analysis setup and use

Install `requirements.txt` using the Windows setup below. RapidOCR runs locally
on CPU through ONNX Runtime. No external explanation API key is needed.

On Home, expand **Analyze a Meme**:

1. Upload one JPEG, PNG or static WebP (up to 10 MB and 20 megapixels).
2. Check the normalized, metadata-free preview. Processing uses at most
   1600 pixels per side; animated and corrupt images are rejected.
3. Click **Read text locally** to run OCR and local template identification.
   OCR downloads its small models on first use, then reuses the local cache.
4. Optionally correct the visible text and review **Template context**.
5. Use **Related memes** to find templates using the visible/corrected text.
6. Use **Clear image** to discard the upload and its results. Replacing the
   upload clears prior analysis; editing text clears related search results.

### Local processing and template context

Validation, preview, OCR and matching run on the app's machine (the Streamlit
server on a hosted deployment). Uploaded images and visible text are not sent
to an external explainer or persisted to disk or Supabase. Public references,
indexes and model files are cached under gitignored `.cache/v3/`.
Logout/session expiry clears upload state and resets the uploader.

The local matcher uses prepared references from `memes.json`, lightweight
hashes and optional cached FastEmbed image embeddings. No references/models
are downloaded by the matcher during normal UI use. Prepare references with
`python -m utils.template_index --hash-only` (omit `--hash-only` to prepare
optional CLIP embeddings).

Reliable matches show collection metadata, not an interpretation of the exact
uploaded joke. Unknown or weak matches remain uncertain. Missing references
or image embeddings do not block OCR or related caption search. Metadata
importers reuse reliable local template metadata by default; the generic
explanation/result interface remains available for explicitly supplied providers.

Related suggestions use lexical caption search and shared situations,
categories and emotions, with duplicates and the selected template excluded.
Caption search opts out of the global semantic query cache. Ordinary search
retains its existing semantic fallback.

### Prototype limitations

- Identification is limited to the prepared collection; incomplete indexes
  cannot produce a reliable match.
- Hash matching works best for near-duplicates. Captions, crops, borders and
  remakes can prevent a match. Optional CLIP can confuse similar scenes.
- Matching thresholds are conservative heuristics, not calibrated certainty.
- OCR can miss small, stylized or obscured text. English is the primary tested
  use case; recognition quality in other languages is not guaranteed.
- General visual explanations and cultural or historical verification are
  unavailable. The planned local Meme Explainer is a separate feature.

## Current features

- **Description, emotion, and situation search:** search names, aliases,
  keywords, meanings, descriptions, and contextual metadata.
- **Lexical + semantic/hybrid search:** weighted lexical matching prioritizes
  names and exact context, with conservative typo tolerance. If no lexical
  results qualify, longer queries can use a FastEmbed semantic fallback
  (`BAAI/bge-small-en-v1.5`) to return one confident, unambiguous match.
  Short queries stay lexical-only; semantic search does not rerank lexical
  results. Lexical search remains available if the model cannot load.
- **Categories and filters:** quick category buttons, emotion browsing, and
  advanced category/emotion filters. An empty search with no filters browses
  the whole collection, six templates per page.
- **Meme previews:** remote previews hosted by Imgflip, with a fallback message
  when an image is unavailable.
- **Supabase email authentication:** sign up, log in with email and password,
  and log out through the sidebar Account panel.
- **User profiles:** the app creates or updates the authenticated user's
  Supabase profile record and displays their email in the Account panel.
- **Saved Memes:** signed-in users can save, unsave, and revisit templates in
  their personal Saved library.
- **Recently Viewed:** opening a meme's details while signed in records the
  view; the library shows up to 50 distinct templates, most recent first.
- **Per-meme More details toggle:** show or hide categories, emotions, aliases,
  common situations, description, and keywords independently for each meme.
- **User-specific data:** Supabase Row Level Security (RLS) protects profiles,
  Saved Memes, and Recently Viewed records. App queries also scope library
  operations to the authenticated user, and logout clears private session state.

Try searches such as `distracted boyfriend`, `painful forced smile`,
`2 choices`, or a description of the situation you have in mind.

## Project structure

```text
app.py                  Streamlit app, search, filters, previews, and pagination
ui.css                  App styling
data/memes.json         40 meme templates and their metadata
utils/search.py         Lexical ranking and hybrid search routing
utils/semantic.py       Local text embeddings and semantic fallback
utils/filters.py        Category and emotion filtering
utils/images.py         Remote preview loading and caching
utils/auth.py           Supabase authentication and profile synchronization
utils/account_ui.py     Sidebar account controls
utils/library.py        Saved Memes and Recently Viewed data operations
utils/library_ui.py     Library navigation, save actions, and details toggles
utils/uploads.py        Bounded upload validation and normalized preview
utils/ocr.py            Optional local RapidOCR engine and failure states
utils/template_index.py Explicit reference/model preparation and local index
utils/identification.py Hash/visual matching and abstention
utils/explanations.py   Grounded metadata and related-template retrieval
utils/intelligence.py   Analysis orchestration and partial failure handling
utils/intelligence_ui.py Session-local Home upload interface
utils/vision.py         Generic explanation/result classes and provider interface
tests/                  unittest regression and Streamlit app tests
requirements.txt        App dependencies and local OCR
.streamlit/secrets.toml Local Supabase configuration (ignored; never commit)
```

## Local setup on Windows (PowerShell)

Install Python 3.10 or newer, then open PowerShell in the project directory.
Create and activate a virtual environment:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Install the dependencies from the repository:

```powershell
python -m pip install -r requirements.txt
```

Configure Supabase as described below if you want to use accounts and personal
libraries. Guest browsing and search do not require Supabase credentials.
Internet access is needed for remote previews, Supabase features, and the
initial semantic model download; embeddings run locally after the model loads.

Run the Streamlit app:

```powershell
python -m streamlit run app.py --browser.gatherUsageStats false
```

Open the local address printed by Streamlit (normally localhost on port 8501).
Stop the server with **Ctrl+C**. Run `deactivate` when finished with the environment.

If PowerShell blocks activation, use the virtual environment's Python directly:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py --browser.gatherUsageStats false
```

## Supabase configuration

Account features require a Supabase project with email/password authentication
and the database tables used by the app. If email confirmation is enabled,
confirm the account's email before logging in.

Create `.streamlit/secrets.toml` locally. Set these top-level TOML entries using
your own project settings; the values below are placeholders only:

```toml
SUPABASE_URL = "<YOUR_SUPABASE_PROJECT_URL>"
SUPABASE_PUBLISHABLE_KEY = "<YOUR_SUPABASE_PUBLISHABLE_KEY>"
```

The app expects an HTTPS project URL and a publishable key beginning with
`sb_publishable_`. Do not use a service-role or secret key.
**Local Supabase credentials belong in `.streamlit/secrets.toml`, and this file
must not be committed.** It is already excluded by `.gitignore`. Never put real
project URLs, keys, passwords, or session tokens in this README or tracked files.

The database must support the following records and conflict targets:

| Table | Fields used or expected by the app | Unique key |
| --- | --- | --- |
| `profiles` | `user_id`, `updated_at`, defaulted `created_at`, nullable `display_name` | `user_id` |
| `saved_memes` | `user_id`, `meme_id`, `created_at` | `user_id, meme_id` |
| `recently_viewed` | `user_id`, `meme_id`, `last_viewed_at` | `user_id, meme_id` |

Use the authenticated Supabase user's ID for `user_id` and the template's ID
from `data/memes.json` for `meme_id`. Enable RLS on all three tables and configure
policies so authenticated users can only read or write their own rows
(`auth.uid() = user_id`), including checks on inserted or updated rows.
Allow the own-row operations needed for profile upserts, saving/unsaving,
and recording/fetching recent views. App-side filters do not replace RLS.

The repository does not include a Supabase SQL schema or migrations; provision
these tables, constraints, permissions, and policies in Supabase before using
the account and library features.

## Testing

### Catalog expansion from approved webpages

Maintain `data/catalog_sources.json`, then run `python -m utils.catalog_sources`
(or supply `--config path/to/sources.json`). The initial source list is empty;
add only webpages you have reviewed and approved for crawling:

```json
{
  "limits": {"max_sources": 5, "max_pages": 3, "max_images": 20},
  "sources": [
    {"name": "source-a", "approved": true, "seeds": ["https://example.org/memes"]},
    {"name": "source-b", "approved": false, "seeds": ["https://example.net/templates"]}
  ]
}
```

These example URLs are placeholders. Approval here permits discovery only.
Candidates remain pending until manually approved through `admin_review.py`;
search continues to use only the local catalog. No external meme-search API is used.

Page and image budgets apply per source, with hard ceilings of 10 pages,
100 image attempts and 10 sources; defaults bound a run to 15 pages and 100
image attempts. Oversized configurations fail before crawling; split larger
lists into separate configs. Unapproved sources are skipped. Only explicit
seeds are visited, using the existing robots.txt and download/image protections.
Duplicate normalized seeds are visited once per run; the durable review queue
deduplicates image URLs and content hashes across sources and previous runs,
including rejected candidates. Source failures do not stop subsequent sources.

JSON output reports per-source and overall `pages_processed` (page attempts),
`candidates_discovered` (crawler candidates before queue deduplication),
`candidates_queued`, `skipped` (crawler skips, queue duplicates, unapproved or
duplicate seeds), and `errors`. Unexpected source failures include an `error`
message; interrupted indexing cannot report partial counts. Exit status is 1
if errors occurred, otherwise 0. No candidates are automatically ingested.

From the project root with the virtual environment activated, run:

```powershell
python -m unittest discover -s tests -v
```

To run only the short-query search regressions:

```powershell
python -m unittest discover -s tests -p "test_search_short.py" -v
```

Without activation, replace `python` with `.\.venv\Scripts\python.exe`.
The suite covers dataset validation, search and semantic fallback, filters,
preview handling, authentication, profiles, library operations, and Streamlit
interactions. Authentication and library tests use mocked clients; they do not
validate a live Supabase project's RLS policies.

V3 tests cover upload formats/limits/orientation, OCR failures, hash and visual
matching decisions, cache preparation/reuse, metadata fidelity, deduplication,
partial failures, upload replacement/clearing and Streamlit result rendering.
Generic provider tests cover corrected OCR, reliable hint selection, explicit
provider injection, failure handling and the unavailable default explainer.
Model/network calls are mocked in unit tests. Upload integration tests exercise
validation, local analysis, editing, clearing and related retrieval through
Streamlit. Run a browser upload smoke test before release.

For a live isolation check, use two different accounts: save different memes
and open different details under each account, then verify Saved and Recently
Viewed show only that account's records after switching accounts.

## V2 status

V2 has been live-tested with two different user accounts for Saved Memes and
Recently Viewed isolation. This is the reported V2 validation status; the
local automated tests separately cover application behavior with mocked services.

## Future roadmap

- Meme creation and remixing.
- Video/GIF support.
- Future GIF and sticker discovery and creation features.

These are future features and are not part of V3. The sidebar Explore and Categories navigation entries
are disabled placeholders; the category filters described above are available.
