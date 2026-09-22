"""Reusable catalog metadata suggestions; no UI state or persistence."""

import re

from utils.importer import LIST_FIELDS, normalize_list
from utils.intelligence import analyze, explain_upload, reliable_template
from utils.search import STOP_WORDS
from utils.uploads import validate_upload


FIELDS = ("name", "meaning", *LIST_FIELDS)


def suggest_metadata(content, memes, *, provider=None):
    """Return (metadata, notice) from image bytes and reference records.

    Indexers can optionally supply a generic explanation provider.
    By default, suggestions use reliable local template metadata only.
    Invalid images raise UploadError. Analysis does not save or import records.
    """
    upload = validate_upload(content)
    local = analyze(upload, memes)
    matched = reliable_template(local, memes)
    suggestions = {field: matched.get(field, "") for field in FIELDS} if matched else {}
    vision = explain_upload(upload, local, memes, provider=provider)
    if vision.status == "ok" and vision.explanation is not None:
        explanation = vision.explanation
        suggestions["meaning"] = explanation.expression
        # Use grounded wording and the collection's vocabulary, without another
        # model request or inventing template identities/aliases.
        evidence = " ".join((explanation.expression, explanation.observations,
                             explanation.why_it_works)).lower()
        if not matched:
            words = re.findall(r"[a-z]+(?:'[a-z]+)?", evidence)
            suggestions["keywords"] = normalize_list(",".join(
                word for word in words if len(word) > 3 and word not in STOP_WORDS))[:12]
            suggestions["situations"] = [explanation.expression]
            for field in ("emotions", "categories"):
                vocabulary = sorted({tag for meme in memes for tag in meme.get(field, [])})
                suggestions[field] = [tag for tag in vocabulary
                                      if re.search(r"(?<!\w)" + re.escape(tag.lower()) + r"(?!\w)", evidence)][:6]
        notice = "Metadata suggestions generated."
    elif matched:
        notice = "Used reliable template metadata; image explanation was unavailable."
    else:
        return {}, vision.message or "Analysis unavailable."
    return suggestions, notice

