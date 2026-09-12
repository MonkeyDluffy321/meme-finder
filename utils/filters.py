"""Metadata filtering that preserves search relevance and original records."""


def filter_options(memes, field):
    return sorted({tag for meme in memes for tag in meme.get(field, [])})


def filter_memes(memes, categories=(), emotions=()):
    """Match any selected tag within a group, and require both active groups."""
    categories, emotions = set(categories), set(emotions)
    return [meme for meme in memes
            if (not categories or categories.intersection(meme.get("categories", [])))
            and (not emotions or emotions.intersection(meme.get("emotions", [])))]
