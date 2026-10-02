"""Independent finished-meme and existing template search pipelines."""

import re
import unicodedata

from utils import external_index, meme_search, search, semantic


def _identity_labels(row):
    # Identity normalization must not use query synonyms or fuzzy matching.
    def normalize(label):
        return tuple(re.findall(r"\w+", unicodedata.normalize("NFKC", label).casefold()))
    name = normalize(row.get("name", ""))
    labels = {normalize(label) for label in row.get("aliases", [])}
    labels.add(name)
    labels.discard(())
    return name, labels


def _keys(row):
    """Only shared explicit identities/URLs prove duplicates, never keywords."""
    keys = set()
    if row.get("image_url"):
        keys.add(("image", row["image_url"]))
    for ref in [row, *row.get("provenance", [])]:
        if ref.get("provider") and ref.get("template_id"):
            keys.add(("source", ref["provider"], ref["template_id"]))
    return keys


def combine_templates(curated, external, query):
    curated = list(curated)
    names = set()
    owners = {}
    for index, row in enumerate(curated):
        name, labels = _identity_labels(row)
        if name:
            names.add(name)
        for label in labels:
            owners.setdefault(label, set()).add(index)
    seen = set()
    combined = []
    for source, rows in enumerate((curated, external)):
        for position, row in enumerate(rows):
            if source:
                name, labels = _identity_labels(row)
                matches = set().union(*(owners.get(label, set()) for label in labels))
                if name in names or len(matches) == 1:
                    continue
            keys = _keys(row)
            if keys & seen:
                continue
            seen.update(keys)
            query_words = search.normalized_words(query)
            labels = [search.normalized_words(label)
                      for label in [row.get("name", ""), *row.get("aliases", [])]]
            exact = any(label == query_words for label in labels)
            recovered = any(search.name_similarity(query_words, label) >= 82 for label in labels)
            tier = 0 if exact else 1 if recovered else 2
            combined.append((tier, source, position, row))
    combined.sort(key=lambda item: item[:3])
    return [item[3] for item in combined]


def search_all(query, templates, *, include_finished=True, include_external=True):
    # Caption text keeps its original meaning; only V3 uses V3 query aliases.
    memes = meme_search.search_finished_memes(query) if include_finished else []
    templates = list(templates)
    template_query = search.normalize_query(query)
    if not template_query.strip() or not include_external:
        matches = search.search_memes(templates, template_query, require_strong=True)
        return {"memes": memes, "templates": matches}
    template_query = search.normalize_hinglish_query(template_query, templates)
    curated = search.search_memes(templates, template_query, use_semantic=False,
                                 require_strong=True, strong_only=True)
    external = external_index.search_external_templates(template_query, lexical_only=True)
    matches = combine_templates(curated, external, template_query)
    if not matches:
        matches = semantic.semantic_fallback(templates, template_query)
        if not matches and len(search.normalized_words(template_query)) >= 4:
            matches = external_index.search_external_templates(template_query, semantic_only=True)
    return {"memes": memes, "templates": matches}
