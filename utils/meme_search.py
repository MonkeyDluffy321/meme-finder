"""Deterministic finished-meme retrieval, independent of V3 template ranking."""

from copy import deepcopy
import re

from utils.meme_index import INDEX_PATH, load_index, normalize_caption


_FILLER = set("a an the is are am was were i me my you your it this that of to and with for in on at what when how show find meme memes".split())


def _tokens(text):
    return set(re.findall(r"\w+(?:'\w+)?", normalize_caption(text).replace("’", "'"))) - _FILLER


def _evidence(row, query, tokens):
    """Score each transcription separately; metadata may support caption tokens."""
    best = None
    for caption in row.get("caption_variants", [row["caption_text"]]):
        fields = ((caption, 6), (" ".join(row["topics"]), 4), (row["situation"], 4),
                  (row["template_name"] + " " + row["template_id"], 1))
        weights = {}
        for text, weight in fields:
            for token in tokens & _tokens(text):
                weights[token] = max(weight, weights.get(token, 0))
        exact = normalize_caption(caption) == query
        coverage = len(weights) / len(tokens)
        # Reject incidental overlap and metadata-free arbitrary results.
        if not exact and (coverage < 0.6 or (len(tokens) > 1 and len(weights) < 2)):
            continue
        caption_tokens = _tokens(caption)
        caption_coverage = len(tokens & caption_tokens) / len(tokens)
        score = sum(weights.values()) / len(tokens) + 2 * caption_coverage
        evidence = (int(exact), coverage, score)
        if best is None or evidence > best:
            best = evidence
    return best


def search_finished_memes(query, *, index_path=INDEX_PATH, limit=20):
    """Return fresh finished-meme records, not template-shaped search adapters.

    Exact caption > query coverage > weighted field relevance > source quality.
    Perceptual copies remain eligible with a small relevance demotion. No models,
    downloads, provider calls or process-wide caption/query caches are used.
    """
    if not isinstance(query, str) or len(query) > 5000 or type(limit) is not int or limit <= 0:
        return []
    query = normalize_caption(query)
    tokens = _tokens(query)
    if not tokens:
        return []
    ranked = []
    for row in load_index(index_path):
        evidence = _evidence(row, query, tokens)
        if evidence is None:
            continue
        exact, coverage, score = evidence
        if row.get("possible_duplicate_of"):
            score *= 0.9
        confidence = max(({"unknown": 0, "reported": 1, "verified": 2}.get(
            reference.get("source_confidence"), 0) for reference in row["provenance"]), default=0)
        ranked.append(((-exact, -coverage, -score, -confidence, row["instance_key"]), row))
    ranked.sort(key=lambda item: item[0])
    return deepcopy([row for _, row in ranked[:limit]])
