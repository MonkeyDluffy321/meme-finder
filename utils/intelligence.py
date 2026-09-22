"""Image analysis has no database calls and persists no user content."""

from utils.ocr import extract_text, OCRResult
from utils.template_index import read_index, embed_images
from utils.identification import identify, Identification
from utils.explanations import explain
from utils.vision import VisionResult


def reliable_template(result, memes):
    identity = result["identification"]
    if identity.status != "likely" or not identity.candidates:
        return None
    return next((m for m in memes if m["id"] == identity.candidates[0]["id"]), None)


def explain_upload(upload, local_result, memes, corrected_text=None, provider=None):
    """Use an explicitly supplied provider; no default explainer is installed."""
    if provider is None:
        return VisionResult("unavailable", message="Image explanation unavailable. A local Meme Explainer is planned separately.")
    matched = reliable_template(local_result, memes)
    hint = explain(matched) if matched else None
    original = local_result["ocr"].text
    correction = corrected_text if corrected_text is not None and corrected_text != original else None
    try:
        return provider.explain(upload.preview, original, correction, hint)
    except Exception:
        return VisionResult("error", message="Image explanation unavailable. Please try again later.")


def analyze(upload, memes):
    notices = []
    try:
        ocr = extract_text(upload.image)
    except Exception:
        ocr = OCRResult("failed")
    try:
        rows = read_index(memes)
        if len(rows) < len(memes):
            notices.append(f"Reference coverage: {len(rows)}/{len(memes)} templates. Prepare references to retry missing images.")
        vector = None
        if rows and all(r.get("embedding") is not None for r in rows):
            try:
                vector = embed_images([upload.image])[0]
            except Exception:
                notices.append("Image model unavailable; using hash-only matching.")
        identification = identify(upload.image, rows, vector)
        if len(rows) < len(memes) and identification.status == "likely":
            identification.status = "possible"
    except Exception:
        identification = Identification("unavailable")
    return {"ocr": ocr, "identification": identification, "notices": notices}
