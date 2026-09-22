"""Deterministic explanations from local metadata and lexical retrieval only."""

from dataclasses import dataclass
import re

from utils.explanations import explain, related_memes
from utils.intelligence import reliable_template
from utils.vision import Explanation, VisionResult


@dataclass
class LocalExplanation(Explanation):
    template_name: str | None
    situations: list[str]
    visible_text: str
    text_source: str
    related: list[dict]
    intent: str
    answer: str


def question_intent(question):
    text = question.lower().strip()
    if not text:
        return "overview"
    for intent, pattern in (
        ("similar", r"\b(similar|related)\b"),
        ("caption", r"\b(text|caption|wording|words)\b"),
        ("usage", r"\b(when|use|usage|situations?)\b"),
        ("humor", r"\b(why|funny|humou?r|works?)\b"),
        ("meaning", r"\b(mean|means|meaning|express|explain)\b"),
    ):
        if re.search(pattern, text):
            return intent
    return "unsupported"


def caption_reading(text):
    """Conservative text patterns; quoted clauses remain claims by the caption."""
    text = text.strip()
    clause = r"(.+?)"
    for pattern, label in (
        (r"expectation\s*:\s*" + clause + r"\s+reality\s*:\s*(.+)", "expectation"),
        (r"me\s*:\s*" + clause + r"\s+also me\s*:\s*(.+)", "self"),
        (r"i\s+" + clause + r"\s+but\s+(.+)", "contrast"),
    ):
        match = re.fullmatch(pattern, text, re.I | re.S)
        if match:
            first, second = (part.strip() for part in match.groups())
            if label == "expectation":
                return (f'The caption contrasts the hoped-for outcome, "{first}", with the reported reality, "{second}".',
                        "The expectation/reality framing invites humor from the gap between the hoped-for and reported outcomes.")
            if label == "self":
                return (f'The caption pairs the speaker\'s first statement, "{first}", with another statement or action by the same speaker, "{second}".',
                        "The 'me / also me' framing invites a comparison of the speaker's statements and behavior; if they conflict, that inconsistency can be self-deprecating humor.")
            return (f'The speaker reports "I {first}" but contrasts it with "{second}".',
                    "The word 'but' frames a contrast. That may create irony if the second clause undercuts the first; contrast alone does not prove a joke.")
    match = re.fullmatch(r"when\s+(.+)", text, re.I | re.S)
    if match and len(match[1].split()) >= 3:
        return (f'The caption sets up the situation "{match[1].strip()}" and presents the image as a reaction to it.',
                "The caption supplies a situation for the image to react to. Without clear reaction evidence, the precise humor remains uncertain.")
    # A small literal fallback for recognizable English statements, not arbitrary OCR.
    if re.search(r"\b(?:i|we|you|they|he|she|it)\s+(?:am|is|are|was|were|have|has|want|need|love|hate|feel|forgot|tried|said|can|can't|cannot|will|won't|don't|do not)\b", text, re.I):
        return (f'The caption says "{text}". It presents this as the speaker\'s statement or experience; the wording alone does not verify it.',
                "No clear humorous reversal is established by this wording alone; the image or additional context may supply the joke.")
    return None


def explain_local(local_result, memes, corrected_text=None, question=""):
    """Explain caption evidence first; captions/search never establish identity.

    An explicit correction, including an empty string, replaces raw OCR.
    This function performs no OCR, model loading, secret access or image I/O.
    """
    matched = reliable_template(local_result, memes)
    metadata = explain(matched) if matched else {}
    text = corrected_text if corrected_text is not None else local_result["ocr"].text
    source = "User-corrected visible text" if corrected_text is not None else "Raw OCR (may contain errors)"
    related = related_memes(memes, matched, text)
    situations = list(metadata.get("situations", []))
    description = metadata.get("description") or "No reliable scene description is available."
    meaning = metadata.get("meaning") or "There is not enough reliable metadata to explain this meme's meaning."
    reading = caption_reading(text)
    useful_text = reading is not None
    usable_caption = len(re.findall(r"[A-Za-z]{2,}", text)) >= 2
    reliable_context = bool(matched and (metadata.get("meaning") or metadata.get("description")))
    observations = source + ": " + text if text.strip() else "No visible text was supplied or detected."
    if reading:
        expression, why = reading
    elif usable_caption and reliable_context:
        expression = f'The caption "{text}" supplies the subject or situation of the uploaded meme.'
        why = "The exact relationship between the caption's parts is uncertain."
    else:
        expression = "The available caption is insufficient for a supported text-level interpretation."
        why = "There is insufficient evidence to explain the uploaded joke."
    if reliable_context:
        if usable_caption:
            expression += (f' Applied to "{text}", the likely template convention suggests this reaction: '
                           + meaning + " This connection is tentative if the caption contradicts that convention.")
            why += (f' For this caption, "{text}", the template supplies the conventional reaction "{meaning}". '
                    "The possible joke is the pairing of that reaction with the caption's situation, rather than the template by itself.")
        else:
            expression += " The reliable template supplies limited context: " + meaning
        observations += " Supporting collection description: " + description
    uncertainty = ("Visual/template context is uncertain. " if not matched else
                   "Template identification is supporting context, not proof of the uploaded joke. ")
    uncertainty += ("This is a local text-level reading, not general visual understanding. "
                    "Identity, origin, slang and cultural context are not inferred from OCR or search suggestions.")
    caption = observations + " " + expression
    usage = ("Documented situations:\n" + "\n".join("- " + item for item in situations)
             if situations else "No grounded usage situations are available for this image.")
    similar = ("Related collection suggestions (not identifications of this image):\n" +
               "\n".join(item["name"] + ": " + item.get("meaning", "") for item in related)
               if related else "No related collection matches were found from the available text or metadata.")
    intent = question_intent(question)
    answer = {"overview": expression, "meaning": expression, "humor": why,
              "usage": usage, "caption": caption, "similar": similar,
              "unsupported": "I can help with meaning, why it works, usage, visible text, or similar memes using local evidence."}[intent]
    explanation = LocalExplanation(
        observations=observations, expression=expression, why_it_works=why,
        wording=[caption], uncertainty=uncertainty,
        template_name=metadata.get("name") or None, situations=situations,
        visible_text=text, text_source=source, related=related, intent=intent, answer=answer,
    )
    status = "ok" if useful_text or (usable_caption and reliable_context) else "limited" if reliable_context else "abstained"
    return VisionResult(status, explanation)
