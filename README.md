# Meme Finder V3

Meme Finder V3 is a Python and Streamlit app for finding meme templates by
name, description, emotion, or situation. The current collection contains
**40 meme templates**, with searchable metadata and remote image previews.
Browse and search as a guest, or sign in to keep a personal meme library.

V3 adds **Explain a Meme** on Home. It explains arbitrary uploaded memes and
screenshots using local OCR and, on an explicit click, Gemini visual understanding.
The 40-template collection is optional supporting context, not a requirement
for explanation. V2 search, filters and library behavior remain available.

## Meme explanation setup and use

Install `requirements.txt` in your virtual environment using the Windows setup
below. RapidOCR runs locally on CPU through ONNX Runtime. General visual
explanation uses the official `google-genai==2.23.0` SDK and
`gemini-3.5-flash-lite` (configured by `MODEL` in `utils/vision.py`).
No Tesseract, PyTorch, GPU or Supabase schema change is needed.

### Gemini configuration

Create a Gemini API key in [Google AI Studio](https://aistudio.google.com/apikey).
Add this top-level entry to the existing gitignored `.streamlit/secrets.toml`
using your own key; do not commit the file:

```toml
GEMINI_API_KEY = "<YOUR_GEMINI_API_KEY>"
```

The vision provider accesses only `GEMINI_API_KEY`, and only when the Explain
button is pressed. Missing configuration leaves local features usable.
Availability, free-tier quotas and paid usage depend on your Google project;
check [Gemini API pricing](https://ai.google.dev/gemini-api/docs/pricing).
No fallback model is selected silently when the configured model is unavailable.

On Home, expand **Explain a Meme**:

1. Upload one JPEG, PNG or static WebP (up to 10 MB and 20 megapixels).
2. Check the normalized, metadata-free preview. Processing uses at most
   1600 pixels per side; animated and corrupt images are rejected.
3. Click **Read text locally** and optionally correct the visible text.
   OCR downloads its small models on first use, then reuses the local cache.
4. Review the cloud disclosure and click **Explain this meme**. OCR is optional:
   missing/unreadable text never blocks the image-based request.
5. Read observations, the apparent meaning, why the joke/reaction works,
   supported wording/references, and uncertainty or missing context.
6. Optionally expand **Template context** or **Related memes**.
7. Use **Clear image** to discard the upload and its results. Editing text or
   replacing the upload invalidates the prior explanation without sending again.

### Privacy and request behavior

Validation, preview and OCR run on the app's machine (the Streamlit server on
a hosted deployment). Uploading, running OCR, editing text and Streamlit reruns
do not send the image to Gemini. Only **Explain this meme** sends normalized PNG
bytes, OCR text, any corrected text, and an optional reliable template hint.
The request uses inline bytes, not the provider Files API. Each click makes one
Interactions API `client.interactions.create(...)` call with `store=False`,
automatic retries disabled and an explicit 30-second HTTP timeout. Structured
JSON output is validated before display; incomplete or malformed results use
the local fallback.

Google processes the submitted content under its API terms; free-tier content
may be used to improve its products. See [Google's API terms](https://ai.google.dev/gemini-api/terms).
Session-local storage in this app does not imply local-only processing by Google.
The app does not persist images, OCR text or explanations to disk, Supabase or
a global content cache, and does not log this content or keys. Only public
references, indexes and model files are stored under gitignored `.cache/v3/`.
Logout/session expiry clears V3 state and resets the uploader. Explanation
never saves a meme or records a recent view.

### Optional template context and fallback

The retained local matcher uses previously prepared references from
`memes.json`, lightweight hashes and optional cached FastEmbed image embeddings.
No references/models are downloaded by the matcher during normal UI use.
Template setup is not part of the explanation flow; the optional developer
preparation command remains `python -m utils.template_index --hash-only`
(omit `--hash-only` to prepare optional CLIP embeddings).

Only a reliable match contributes metadata as a hint. Weak matches are not
sent to Gemini or used as explanation facts. Missing references, an unknown
template or an unavailable image-embedding model do not block Gemini.

Missing keys/SDK, timeouts, quota/rate limits, provider errors or malformed
responses show **Cloud explanation unavailable** and **Limited explanation
available**. OCR and corrected text remain accessible. Reliable matches can
provide general collection metadata; otherwise the app admits that it cannot
reliably explain the image without the provider. Related search still works.

Related suggestions use lexical caption search and shared situations,
categories and emotions, with duplicates and the selected template excluded.
Caption search opts out of V2's global semantic query cache. V2's ordinary
search still uses its existing semantic fallback.

### Prototype limitations

- Explanation supports images outside the collection. Identification alone
  remains limited to 40 templates; incomplete indexes cannot produce a reliable hint.
- Hash-only matching works best for near-duplicate templates. Added captions,
  large crops, screenshot borders and remakes can prevent a match. CLIP may
  improve tolerance but can also confuse similar scenes.
- Matching thresholds are conservative prototype heuristics, not calibrated
  accuracy or certainty. Unknown and ambiguous results are expected.
- OCR can miss small, stylized or obscured text. English text is the primary
  tested use case; recognition quality in other languages is not guaranteed.
- Generated explanations can be wrong about sarcasm, slang, cultural references,
  panel relationships or intent. They are interpretations, not verified facts.
  The provider is instructed to distinguish observation from interpretation,
  treat embedded instructions as image content, avoid invented identities,
  origins/events/creators/missing words, and not force humor onto sincere images.
- No web grounding or historical fact verification is performed. Missing context
  should be stated; guardrails and structured validation cannot guarantee factuality.
- The provider interface is replaceable for a future local/Ollama adapter;
  only Gemini is implemented now. No video, remixing or V4/V5 features are added.

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
utils/vision.py         Replaceable vision interface and Gemini Interactions adapter
tests/                  unittest regression and Streamlit app tests
requirements.txt        App dependencies, local OCR and Google GenAI SDK
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
Vision tests cover unknown images, corrected OCR, strict hint selection, missing
keys, timeout/quota/provider errors, malformed output and explicit-click-only
requests. A real SDK test uses a mock HTTP transport to verify serialization and
disabled retries without network access or a real API key. Existing UI test
expectations follow the explanation-first labels; all prior test cases remain.
Model/network calls are mocked in unit tests. AppTest lacks an uploader setter,
so upload integration tests inject that widget boundary and exercise the real
validation and UI. Run a browser upload smoke test before release.

Implementation verification on Windows (Python 3.13): FastEmbed 0.8.0,
ONNX Runtime 1.30.0, RapidOCR 3.9.2 and Pillow 12.3.0 import successfully.
RapidOCR read a generated English text image successfully. Initial public
reference preparation fetched 38/40 images; Success Kid and First World Problems
were unavailable in that attempt. These are local verification observations,
not guarantees about future availability. Google GenAI 2.23.0 was installed after
a successful dependency dry run. Live Gemini access and explanation quality,
browser upload/privacy flow and optional full CLIP inference still require
manual smoke tests. No real Gemini request or missing-reference retry was made
during this change.

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
