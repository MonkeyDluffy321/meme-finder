"""Field-weighted local text search with conservative typo tolerance."""

import re
from collections import Counter
from math import isfinite, log

from rapidfuzz.fuzz import ratio

from utils.semantic import semantic_fallback
from utils import semantic


# Ignore common words so descriptions focus on their useful terms.
STOP_WORDS = {"a", "an", "the", "is", "at", "in", "on", "of", "to", "and", "with"}
CONTEXT_WORDS = {
    "by",
    "another",
    "during",
    "while",
    "situation",
    "scenario",
    "moment",
    "trying",
    "something",
    "thing",
}
STRUCTURED_FIELDS = {"name", "aliases", "keywords", "situations", "emotions", "categories"}
FIELD_WEIGHTS = {
    "name": 8, "aliases": 7, "keywords": 6, "situations": 6,
    "meaning": 3, "emotions": 3, "categories": 3, "description": 1,
}
LIST_FIELDS = {"aliases", "keywords", "situations", "emotions", "categories"}
FUZZY_CUTOFF = 85
SOLO_FUZZY_CUTOFF = 90
MIN_COVERAGE = 0.6
NUMBER_WORDS = (
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight",
    "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen",
    "sixteen", "seventeen", "eighteen", "nineteen", "twenty",
)
DIGIT_WORDS = {str(number): word for number, word in enumerate(NUMBER_WORDS)}
IRREGULAR_WORDS = {"women": "woman", "men": "man"}
QUERY_ALIASES = {
    "uncomfortable": "awkward",
    "embarrassing": "embarrassment",
    "embarrassed": "embarrassment",
    "ignore": "avoid",
    "ignoring": "avoid",
    "choice": "decision",
    "choices": "decision",
}


def normalize_query(text):
    """Canonicalize only explicit whole-token aliases before hybrid search."""
    text = re.sub(
        r"\w+",
        lambda match: QUERY_ALIASES.get(
            match.group().lower(),
            match.group()
        ),
        text,
    )

    return re.sub(
        r"\w+",
        lambda match: IRREGULAR_WORDS.get(
            match.group().lower(),
            match.group()
        ),
        text,
    )


def normalized_words(text):
    """Normalize case, digits 0-20, and two explicit irregular plurals."""
    return [DIGIT_WORDS.get(word, word)
            for word in re.findall(r"\w+", normalize_query(text).lower())]


def fuzzy_eligible(word):
    """Numbers require exact matches, including their normalized word forms."""
    return len(word) >= 5 and not any(char.isdigit() for char in word) and word not in NUMBER_WORDS


def tokenize(text):
    """Return lowercase words, excluding common filler words."""
    return set(normalized_words(text)) - STOP_WORDS


def metadata_items(meme):
    """Keep list-item boundaries and support records without optional metadata."""
    for field in FIELD_WEIGHTS:
        values = meme.get(field, []) if field in LIST_FIELDS else [meme.get(field, "")]
        for value in values:
            yield field, normalized_words(value), tokenize(value)


def name_similarity(query_words, name_words):
    """Recover multi-token names without relaxing general token matching.

    Every ordered token must align; short words and numbers must be exact.
    At least one token must be a strong anchor, even when others have typos.
    """
    if len(query_words) < 2 or len(query_words) != len(name_words):
        return 0
    scores = []
    for word, candidate in zip(query_words, name_words):
        if word == candidate:
            scores.append(100)
        elif fuzzy_eligible(word) and fuzzy_eligible(candidate):
            scores.append(ratio(word, candidate))
        else:
            return 0
    if min(scores) < 70 or max(scores) < 90:
        return 0
    return ratio(" ".join(query_words), " ".join(name_words), score_cutoff=82)


def search_memes(memes, query, *, use_semantic=True, require_strong=False):
    """Admit useful evidence, then rank complete names, exact context, and typos.

    IDF counts each record once. Equal ranks retain input order and results
    remain the original objects. Descriptive queries can boost weak lexical
    matches; exact tiers and recovered names retain their lexical ordering.
    require_strong gates tier acceptance using existing lexical evidence;
    semantic-only results cannot terminate a multi-source fallback search.
    """
    query = normalize_query(query)
    memes = list(memes)
    if not query.strip():
        return list(memes)

    query_words = tokenize(query) - CONTEXT_WORDS
    if not query_words:
        return []

    phrase_words = normalized_words(query)
    phrase = " " + " ".join(phrase_words) + " "
    items = [list(metadata_items(meme)) for meme in memes]
    frequencies = Counter(word for record_items in items
                          for word in set().union(*(item[2] for item in record_items)))
    idf = {word: log(1 + (len(memes) - count + 0.5) / (count + 0.5))
           for word, count in frequencies.items()}
    evidence_words = query_words
    short_query = len(query_words) <= 2
    name_scores = [max((name_similarity(phrase_words, words)
                       for field, words, _ in record_items if field in {"name", "aliases"}),
                      default=0) for record_items in items]
    ordered_scores = sorted(name_scores, reverse=True)
    runner_up = ordered_scores[1] if len(ordered_scores) > 1 else 0
    ranked = []
    protected = set()
    strong_match = False
    for index, (meme, record_items) in enumerate(zip(memes, items)):
        best_scores = dict.fromkeys(sorted(evidence_words), 0.0)
        similarities = dict.fromkeys(sorted(evidence_words), 0.0)
        phrase_bonus = 0
        complete_name = False
        coherent_count = 0
        short_support = set()
        for field, words, field_words in record_items:
            weight = FIELD_WEIGHTS[field]
            complete_name |= field in {"name", "aliases"} and words == phrase_words
            normalized = " " + " ".join(words) + " "
            if len(phrase_words) > 1 and phrase in normalized:
                phrase_bonus = max(phrase_bonus, 2 * weight)
            coherent_count = max(coherent_count, len(evidence_words & field_words))
            for word in best_scores:
                if word in field_words:
                    similarity = 100
                    token_score = weight * idf[word]
                elif fuzzy_eligible(word):
                    matches = [(ratio(word, candidate, score_cutoff=FUZZY_CUTOFF), candidate)
                               for candidate in sorted(field_words) if fuzzy_eligible(candidate)]
                    similarity = max((value for value, _ in matches), default=0)
                    # Weight fuzzy evidence by the matched corpus term, not an
                    # unseen misspelling's artificially high rarity.
                    token_score = max((weight * 0.75 * value / 100 * idf[candidate]
                                       for value, candidate in matches), default=0)
                else:
                    similarity = token_score = 0
                best_scores[word] = max(best_scores[word], token_score)
                similarities[word] = max(similarities[word], similarity)
                # Short queries need explicit metadata evidence. A complete
                # prose item also qualifies; a prose fragment only qualifies
                # in meaning when it is selective (at most 10% of records).
                explicit = field in STRUCTURED_FIELDS or field_words == evidence_words
                selective_meaning = (field == "meaning" and word in field_words
                                     and frequencies[word] <= max(1, len(memes) * 0.1))
                # When the corpus knows this exact term, do not add unrelated
                # fuzzy neighbours (e.g. money -> monkey). Unknown typos can
                # still use the existing conservative fuzzy thresholds.
                supported_match = similarity == 100 or (
                    similarity >= SOLO_FUZZY_CUTOFF and (
                        word not in frequencies or (
                            field in {"name", "aliases"} and len(words) == 1)))
                if supported_match and (explicit or selective_meaning):
                    short_support.add(word)

        matched = [value for value in similarities.values() if value]
        coverage = len(matched) / len(evidence_words)
        recovered_name = name_scores[index] >= 82 and name_scores[index] - runner_up >= 5
        admitted_tokens = coverage >= MIN_COVERAGE and not (
            len(matched) == 1 and matched[0] < SOLO_FUZZY_CUTOFF)
        if short_query:
            # Two-token searches can use an incidental second clue, but need
            # at least one explicit anchor and the existing overall coverage.
            admitted_tokens &= bool(short_support)
        if not complete_name and not (admitted_tokens or recovered_name):
            continue
        exact_coverage = sum(value == 100 for value in similarities.values()) / len(evidence_words)
        coherent = coherent_count / len(evidence_words)
        strong_exact = exact_coverage >= MIN_COVERAGE and (
            phrase_bonus > 0 or coherent >= MIN_COVERAGE)
        tier = 3 if complete_name else 2 if strong_exact else 1
        strong_match |= (tier >= 2 or recovered_name
                         or (short_query and short_support == evidence_words))
        score = (sum(best_scores.values()) * (1 + 0.25 * coherent) + phrase_bonus) * coverage
        if recovered_name:
            score += FIELD_WEIGHTS["name"] * name_scores[index] / 100
            protected.add(id(meme))
        ranked.append((tier, score, meme))

    if require_strong and not strong_match:
        return []
    ranked.sort(key=lambda item: item[:2], reverse=True)
    if ranked:
        if (use_semantic and semantic.descriptive_query(query)
                and any(tier == 1 and id(meme) not in protected for tier, _, meme in ranked)):
            ranked = _hybrid_rank(memes, query, ranked, protected)
        return [meme for tier, score, meme in ranked]
    return semantic_fallback(memes, query) if use_semantic else []


def _hybrid_rank(memes, query, ranked, protected):
    """Bound semantic boosts to 35% of the largest weak lexical score.

    Preserve protected slots. Recover at most one unambiguous semantic-only
    result after lexical results, using the existing fallback thresholds.
    """
    try:
        scores = semantic.semantic_scores(memes, query)
        identities = {id(meme) for meme in memes}
        if not scores or any(id(meme) not in identities or not isfinite(score)
                             or not -1 <= score <= 1 for meme, score in scores):
            return ranked
        similarities = {id(meme): score for meme, score in scores}
        weak = [(tier, score, meme) for tier, score, meme in ranked
                if tier == 1 and id(meme) not in protected]
        scale = max(score for _, score, _ in weak)
        boosted = []
        for tier, score, meme in weak:
            confidence = max(0, similarities.get(id(meme), 0) - semantic.SEMANTIC_THRESHOLD)
            bonus = 0.35 * scale * confidence / (1 - semantic.SEMANTIC_THRESHOLD)
            boosted.append((tier, score + bonus, meme))
        positions = {id(meme): index for index, meme in reversed(list(enumerate(memes)))}
        boosted.sort(key=lambda item: (-item[1], positions[id(item[2])]))
        replacements = iter(boosted)
        result = [next(replacements) if tier == 1 and id(meme) not in protected
                  else (tier, score, meme) for tier, score, meme in ranked]
        ordered = sorted(scores, key=lambda item: item[1], reverse=True)
        best, score = ordered[0]
        runner_up = ordered[1][1] if len(ordered) > 1 else 0
        if (score >= semantic.SEMANTIC_THRESHOLD and score - runner_up >= semantic.SEMANTIC_MARGIN
                and all(best is not meme for _, _, meme in ranked)):
            result.append((0, score, best))
        return result
    except Exception:
        return ranked
