import math
import logging
import re
from functools import lru_cache
from threading import RLock


MODEL_NAME = "BAAI/bge-small-en-v1.5"
SEMANTIC_THRESHOLD = 0.64
SEMANTIC_MARGIN = 0.025
_MODEL_LOCK = RLock()
_QUERY_FILLER = set("a an the is at in on of to and with by another during while i am have it for my but someone somebody man guy person woman".split())


@lru_cache(maxsize=1)
def _load_embedding_model():
    """
    Load the embedding model once per Python process.
    Import is delayed so lexical search can still work
    if FastEmbed is unavailable.
    """
    try:
        from fastembed import TextEmbedding
        return TextEmbedding(model_name=MODEL_NAME)
    except Exception:
        # Cache failure too: lru_cache alone does not cache raised exceptions.
        logging.getLogger(__name__).warning("Semantic model unavailable; using lexical search.")
        return None


def get_embedding_model():
    with _MODEL_LOCK:
        return _load_embedding_model()


def embed_texts(texts):
    """Return embeddings for a list of strings."""
    model = get_embedding_model()
    if model is None:
        raise RuntimeError("Semantic model unavailable")
    return list(model.embed(texts))


@lru_cache(maxsize=4)
def _document_embeddings(model_name, documents):
    return tuple(embed_texts(documents))


@lru_cache(maxsize=128)
def _query_embedding(model_name, query):
    return embed_texts([query])[0]


def cosine_similarity(vector_a, vector_b):
    """Calculate cosine similarity without extra dependencies."""
    dot = sum(float(a) * float(b) for a, b in zip(vector_a, vector_b))

    magnitude_a = math.sqrt(
        sum(float(a) * float(a) for a in vector_a)
    )
    magnitude_b = math.sqrt(
        sum(float(b) * float(b) for b in vector_b)
    )

    if magnitude_a == 0 or magnitude_b == 0:
        return 0.0

    return dot / (magnitude_a * magnitude_b)


def build_semantic_text(meme):
    """
    Build the meaning-focused text used for semantic retrieval.
    Image URLs and unrelated presentation data are intentionally excluded.
    """

    parts = [
        meme.get("name", ""),
        meme.get("meaning", ""),
        meme.get("description", ""),
    ]

    for field in (
        "aliases",
        "situations",
        "emotions",
        "categories",
        "keywords",
    ):
        values = meme.get(field, [])

        if isinstance(values, list):
            parts.extend(str(value) for value in values)

    return ". ".join(
        part.strip()
        for part in parts
        if isinstance(part, str) and part.strip()
    )


def semantic_scores(memes, query):
    """
    Return (meme, similarity) pairs sorted by semantic similarity.

    This does NOT decide whether a result is good enough.
    Admission thresholds belong in the hybrid search layer.
    """

    if not query or not query.strip() or not memes:
        return []

    documents = [
        build_semantic_text(meme)
        for meme in memes
    ]

    embeddings = _document_embeddings(MODEL_NAME, tuple(documents))
    query_embedding = _query_embedding(MODEL_NAME, query.strip())
    if len(embeddings) != len(memes):
        raise ValueError("Incomplete semantic document embeddings")

    scored = []

    for meme, embedding in zip(memes, embeddings):
        if len(query_embedding) != len(embedding):
            raise ValueError("Mismatched semantic vector dimensions")
        score = cosine_similarity(
            query_embedding,
            embedding,
        )

        scored.append((meme, score))

    return sorted(
        scored,
        key=lambda item: item[1],
        reverse=True,
    )


def descriptive_query(query):
    """Require at least four distinct non-filler words before embedding."""
    return len(set(re.findall(r"\w+", query.lower())) - _QUERY_FILLER) >= 4


def semantic_fallback(memes, query):
    """Conservative Tier 4: return one confident, unambiguous match or abstain.

    Thresholds calibrated on the current dataset and unchanged text builder.
    Short queries stay lexical-only. Never called to rerank lexical results.
    """
    if not memes or not descriptive_query(query):
        return []
    try:
        scores = semantic_scores(memes, query)
        if not scores or any(not math.isfinite(score) for _, score in scores):
            return []
        best, score = scores[0]
        runner_up = scores[1][1] if len(scores) > 1 else 0.0
        if score >= SEMANTIC_THRESHOLD and score - runner_up >= SEMANTIC_MARGIN:
            return [best]
    except Exception:
        logging.getLogger(__name__).debug("Semantic fallback failed", exc_info=True)
    return []
