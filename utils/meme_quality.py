"""Conservative, deterministic caption checks. No network, models or image inspection."""

from collections import Counter
import re
import unicodedata


_STRONG = re.compile(r"\b(?:fuck\w*|motherfuck\w*|shit\w*|bullshit|asshole\w*|bitch\w*|bastard\w*|cunt\w*)\b", re.I)
# Explicit acts/promotional imagery, not a general profanity or anatomy blacklist.
_ADULT = re.compile(
    r"\b(?:blowjobs?|handjobs?|gangbangs?|cumshots?|deepthroat(?:ing)?|"
    r"anal sex|oral sex|hardcore porn|porn(?:ographic)? (?:videos?|pics?|images?)|"
    r"send nudes|nude selfies|nude (?:photos?|pics?|women|men)|sex tapes?|masturbat(?:e|ing|ion)|"
    r"cum(?:ming)? (?:in|on) (?:my|your|his|her|a|the) (?:mouth|face|pussy)|"
    r"(?:lick|licking|suck|sucking) (?:my|your|his|her|a|the) (?:cock|dick|pussy)|"
    r"(?:fuck|fucking|penetrate|penetrating) (?:my|your|his|her|a|the) (?:pussy|vagina|anus))\b", re.I)


def _dominant_repetition(tokens):
    """Five non-overlapping copies covering 80% of at least 15 tokens.

    Ignore case/punctuation (already tokenized) and changing numeric counters
    only for this comparison. A small trailing punchline cannot mask flooding.
    """
    if len(tokens) < 15:
        return False
    signature = tuple("<number>" if token.isdecimal() else token for token in tokens)
    for width in range(1, min(12, len(tokens) // 5) + 1):
        phrases = Counter(signature[i:i + width] for i in range(len(signature) - width + 1))
        for phrase, count in phrases.items():
            if count < 5 or count * width < .8 * len(tokens):
                continue
            copies, position = 0, 0
            while position <= len(signature) - width:
                if signature[position:position + width] == phrase:
                    copies += 1
                    position += width
                else:
                    position += 1
            if copies >= 5 and copies * width >= .8 * len(tokens):
                return True
    return False


def caption_quality(caption):
    """Return (skip reason or None, strong-language flag); never rewrite caption."""
    if not isinstance(caption, str) or len(caption) > 5000:
        return "malformed_caption", False
    if any(unicodedata.category(c) in {"Cs", "Cc"} and c not in "\n\r\t" for c in caption):
        return "malformed_caption", False
    # Ignore invisible formatting for analysis, preserving emoji ZWJ and original text on disk.
    text = "".join(c for c in unicodedata.normalize("NFKC", caption)
                   if unicodedata.category(c) != "Cf").strip()
    strong = bool(_STRONG.search(text))
    if not text or all(unicodedata.category(c).startswith("M") or c.isspace() for c in text):
        return "empty_caption", strong
    replacement = text.count("\ufffd")
    mojibake = len(re.findall(r"Ã[\u0080-\u00bf]|Â[\u0080-\u00bf]|â€|ðŸ", text))
    if ((replacement >= 3 and replacement / len(text) >= .1)
            or (mojibake >= 3 and mojibake / len(text) >= .08)):
        return "garbled_text", strong
    flat = " ".join(text.casefold().split())
    if _ADULT.search(flat):
        return "unsafe_adult_content", strong
    tokens = re.findall(r"\w+", flat)
    lines = [" ".join(line.casefold().split()) for line in text.splitlines() if line.strip()]
    if (_dominant_repetition(tokens)
            or (len(tokens) >= 20 and Counter(tokens).most_common(1)[0][1] / len(tokens) >= .8)
            or (len(tokens) >= 40 and any(all(token == tokens[i % width] for i, token in enumerate(tokens))
                                         for width in range(2, 6)))
            or (len(lines) >= 8 and Counter(lines).most_common(1)[0][1] / len(lines) >= .8)
            or re.search(r"(.)\1{119,}", flat)):
        return "repetitive_spam", strong
    if (re.fullmatch(r"https?://\S+", flat) or flat in {"null", "undefined", "[object object]", "lorem ipsum"}
            or (not any(c.isalnum() or unicodedata.category(c) == "So" for c in text)
                and not re.fullmatch(r"[!?… .]{1,8}", text))):
        return "low_information", strong
    return None, strong
