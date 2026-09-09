"""Simple keyword matching with no external services or search libraries."""

import re


# Ignore common words so descriptions focus on their useful terms.
STOP_WORDS = {"a", "an", "the", "is", "at", "in", "on", "of", "to", "and", "with"}


def tokenize(text):
    """Return lowercase words, excluding common filler words."""
    return set(re.findall(r"\w+", text.lower())) - STOP_WORDS


def search_memes(memes, query):
    """Rank partial word matches; prefer names and complete phrase matches.

    An empty query returns the collection in its original order. This is a
    text search, so descriptions work only when they share dataset words.
    """
    if not query.strip():
        return list(memes)

    query_words = tokenize(query)
    if not query_words:
        return []

    ranked = []
    for meme in memes:
        name = meme["name"]
        searchable_text = " ".join(
            [name, meme["meaning"], " ".join(meme["keywords"]), meme["description"]]
        )
        matches = query_words & tokenize(searchable_text)
        if not matches:
            continue

        score = len(matches) + 2 * len(query_words & tokenize(name))
        if query.strip().lower() in searchable_text.lower():
            score += 5
        ranked.append((score, meme))

    ranked.sort(key=lambda item: item[0], reverse=True)
    return [meme for score, meme in ranked]
