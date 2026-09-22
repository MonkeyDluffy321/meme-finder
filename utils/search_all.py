"""Independent finished-meme and existing template search pipelines."""

from utils import external_index, meme_search, search


def search_all(query, templates, *, include_finished=True, include_external=True):
    # Caption text keeps its original meaning; only V3 uses V3 query aliases.
    memes = meme_search.search_finished_memes(query) if include_finished else []
    template_query = search.normalize_query(query)
    matches = search.search_memes(templates, template_query, require_strong=True)
    if not matches and template_query.strip() and include_external:
        matches = external_index.search_external_templates(template_query)
    return {"memes": memes, "templates": matches}
