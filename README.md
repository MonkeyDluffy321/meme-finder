# Meme Finder

A beginner-friendly, local Python app for finding meme templates by name,
keywords, or scene description. The interface uses Streamlit and searches eight
sample entries in a JSON file. No API keys, accounts, database, or cloud services
are required.

## Launch on Windows (PowerShell)

Open PowerShell in this project folder. Python 3.10 or newer is required.
For the first setup, run:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Start the app (also use this command on later visits):

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py --browser.gatherUsageStats false
```

Open http://localhost:8501 in your browser. Stop the server with **Ctrl+C** in
its terminal. You do not need to activate the virtual environment.

On macOS/Linux, create the environment with `python3 -m venv .venv` and use
`.venv/bin/python` instead of `.\.venv\Scripts\python.exe` for the commands above.

## Try it

- `distracted boyfriend`
- `this is fine`
- `guy looking at another girl`
- `dog fire`

An empty search displays the whole collection. Matching ignores capitalization,
punctuation, and common filler words. Results rank shared words, with extra
weight for template names and exact phrases. This is simple text matching, not
AI: unfamiliar wording may need different keywords. Results include each
template's name, short meaning, keywords, and description; no images are bundled.

## Files

```text
app.py              Streamlit page, sidebar, and result cards
requirements.txt    The only direct dependency: Streamlit
data/memes.json     Eight sample meme templates
utils/__init__.py   Marks utils as a Python package
utils/search.py     Local search and ranking helpers
.gitignore          Excludes environment, caches, and local logs
README.md           Setup and usage instructions
```

To extend the collection, add an object to `data/memes.json` with `name`,
`meaning`, `keywords` (a list of strings), and `description`. Keep the file valid
JSON, then refresh the app.

## Later features (not implemented)

The sidebar lists Upload & identify meme, Explain meme, Similar memes, and
Meme creator as a roadmap only. This version does not implement these features.
