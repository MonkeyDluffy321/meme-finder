"""Grounded collection metadata and deduplicated related-template retrieval."""

from utils.search import search_memes


def explain(meme):
    return {key: meme.get(key, [] if key == "situations" else "")
            for key in ("name", "description", "meaning", "situations")}


def related_memes(memes, matched=None, text="", limit=3):
    candidates = []
    if text.strip():
        try:
            # The V2 semantic query cache is process-wide. Keep uploaded caption
            # text out of it; lexical search plus metadata overlap is enough here.
            candidates.extend(search_memes(memes, text.strip()[:5000], use_semantic=False))
        except Exception:
            pass
    if matched:
        def overlap(meme):
            return sum(len(set(meme.get(f, [])) & set(matched.get(f, [])))
                       for f in ("categories", "emotions", "situations"))
        candidates.extend(sorted((m for m in memes if overlap(m)), key=overlap, reverse=True))
    seen = {matched["id"]} if matched else set()
    result = []
    for meme in candidates:
        if meme["id"] not in seen:
            seen.add(meme["id"])
            result.append(meme)
        if len(result) >= limit:
            break
    return result
