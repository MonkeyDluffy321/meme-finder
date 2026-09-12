"""Field-weighted local text search with conservative typo tolerance."""

import re

from rapidfuzz.fuzz import ratio


# Ignore common words so descriptions focus on their useful terms.
STOP_WORDS = {"a", "an", "the", "is", "at", "in", "on", "of", "to", "and", "with"}
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


def normalized_words(text):
    """Normalize case and standalone digits 0-20, preserving word order."""
    return [DIGIT_WORDS.get(word, word) for word in re.findall(r"\w+", text.lower())]


def fuzzy_eligible(word):
    """Numbers require exact matches, including their normalized word forms."""
    return len(word) >= 5 and not any(char.isdigit() for char in word) and word not in NUMBER_WORDS


def tokenize(text):
    """Return lowercase words, excluding common filler words."""
    return set(normalized_words(text)) - STOP_WORDS


def search_memes(memes, query):
    """Rank exact tokens, normalized phrases, and conservative fuzzy tokens.

    Require 60% query-token coverage and stronger evidence for fuzzy-only
    single-token matches. Return original records, preserving order on ties.
    """
    if not query.strip():
        return list(memes)

    query_words = tokenize(query)
    if not query_words:
        return []

    phrase_words = normalized_words(query)
    phrase = " " + " ".join(phrase_words) + " "
    ranked = []
    for meme in memes:
        best_scores = dict.fromkeys(query_words, 0.0)
        similarities = dict.fromkeys(query_words, 0.0)
        phrase_bonus = 0
        for field, weight in FIELD_WEIGHTS.items():
            # Missing metadata supports legacy records; phrases stay within list items.
            values = meme.get(field, []) if field in LIST_FIELDS else [meme[field]]
            field_words = set()
            for value in values:
                field_words.update(tokenize(value))
                normalized = " " + " ".join(normalized_words(value)) + " "
                if len(phrase_words) > 1 and phrase in normalized:
                    phrase_bonus = max(phrase_bonus, 2 * weight)

            for word in query_words:
                if word in field_words:
                    similarity = 100
                    token_score = weight
                elif fuzzy_eligible(word):
                    similarity = max(
                        (ratio(word, candidate, score_cutoff=FUZZY_CUTOFF)
                         for candidate in field_words if fuzzy_eligible(candidate)),
                        default=0,
                    )
                    token_score = weight * 0.75 * similarity / 100
                else:
                    similarity = token_score = 0
                best_scores[word] = max(best_scores[word], token_score)
                similarities[word] = max(similarities[word], similarity)

        matched = [value for value in similarities.values() if value]
        if len(matched) / len(query_words) < MIN_COVERAGE:
            continue
        if len(matched) == 1 and matched[0] < SOLO_FUZZY_CUTOFF:
            continue

        score = (sum(best_scores.values()) + phrase_bonus) * len(matched) / len(query_words)
        ranked.append((score, meme))

    ranked.sort(key=lambda item: item[0], reverse=True)
    return [meme for score, meme in ranked]
