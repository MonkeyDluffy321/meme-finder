# Meme Finder V2

Meme Finder V2 is a Python and Streamlit app for finding meme templates by
name, description, emotion, or situation. The current collection contains
**40 meme templates**, with searchable metadata and remote image previews.
Browse and search as a guest, or sign in to keep a personal meme library.

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
tests/                  unittest regression and Streamlit app tests
requirements.txt        Streamlit, RapidFuzz, FastEmbed, and Supabase dependencies
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

For a live isolation check, use two different accounts: save different memes
and open different details under each account, then verify Saved and Recently
Viewed show only that account's records after switching accounts.

## V2 status

V2 has been live-tested with two different user accounts for Saved Memes and
Recently Viewed isolation. This is the reported V2 validation status; the
local automated tests separately cover application behavior with mocked services.

## Future roadmap

- Image uploads and image understanding to identify memes from pictures.
- Meme creation and remixing.
- Video/GIF support.
- Future GIF and sticker discovery and creation features.

These are future features. The current app searches text metadata and displays
remote template previews. The sidebar Explore and Categories navigation entries
are disabled placeholders; the category filters described above are available.
