"""Optional local RapidOCR provider. Upload text is never globally cached."""

from dataclasses import dataclass
from pathlib import Path
from threading import RLock
import re
from statistics import median

_LOCK = RLock()
_ENGINE = None


@dataclass
class OCRResult:
    status: str
    text: str = ""
    caption: str | None = None

    @property
    def editable_text(self):
        return self.text if self.caption is None else self.caption


def layout_caption(texts, boxes, scores, size):
    """Keep uncertain lines. Require prominent caption evidence before filtering."""
    if boxes is None or scores is None or not len(texts) == len(boxes) == len(scores):
        return None
    width, height = size
    lines = []
    for text, box, confidence in zip(texts, boxes, scores):
        if len(box) != 4:
            return None
        xs, ys = zip(*box)
        # Edge lengths avoid counting a slanted baseline as extra letter height.
        tall = (abs(ys[3]-ys[0]) + abs(ys[2]-ys[1])) / 2
        lines.append((str(text).strip(), min(ys)/height, max(ys)/height,
                      (max(xs)-min(xs))/width, tall, float(confidence)))
    anchors = [line for line in lines if len(line[0].split()) >= 3 and line[3] >= .4 and line[5] >= .7]
    if not anchors:
        return None
    typical = median(line[4] for line in anchors)
    def is_header(line):
        text, top, bottom, span, tall, confidence = line
        return (confidence >= .8 and span < .32 and tall < .75*typical and top < .08
                and min(a[1] for a in anchors) > bottom + .15
                and text.casefold() in {"for you", "following", "explore", "home", "recommended"})

    screenshot_header = any(is_header(line) for line in lines)
    kept = []
    for line in lines:
        text, top, bottom, span, tall, confidence = line
        peripheral = line not in anchors and confidence >= .8 and tall < .75*typical and span < .32
        handle = (bottom > .92 and (re.fullmatch(r"@[\w.]+", text)
                  or screenshot_header and re.fullmatch(r"[a-z][a-z0-9_.]{5,}", text)))
        if not (peripheral and (is_header(line) or handle)):
            kept.append(text)
    return select_caption("\n".join(kept))[:5000]


def select_caption(raw_text):
    """Exclude only isolated decimal-number lines; leave other OCR text intact."""
    return "\n".join(line for line in raw_text.split("\n") if not line.strip().isdecimal())


def get_engine():
    global _ENGINE
    # Failed initialization is retryable on the next explicit analysis.
    if _ENGINE is None:
        from rapidocr import RapidOCR
        cache = Path(__file__).resolve().parents[1] / ".cache" / "v3" / "ocr"
        _ENGINE = RapidOCR(params={
            "Global.model_root_dir": str(cache), "Global.log_level": "error",
            "EngineConfig.onnxruntime.intra_op_num_threads": 2,
            "EngineConfig.onnxruntime.inter_op_num_threads": 1,
        })
    return _ENGINE


def extract_text(image):
    with _LOCK:
        try:
            engine = get_engine()
        except Exception:
            return OCRResult("unavailable")
        try:
            import numpy as np
            # RapidOCR's ndarray interface expects OpenCV BGR order.
            output = engine(np.asarray(image)[:, :, ::-1].copy())
            texts = getattr(output, "txts", None)
            if texts is None:
                return OCRResult("empty")
            scores = getattr(output, "scores", None)
            lines = [str(t).strip() for t in texts if str(t).strip()]
            text = "\n".join(lines)[:5000]
            if not text:
                return OCRResult("empty")
            uncertain = scores is not None and any(float(s) < 0.7 for s in scores)
            caption = layout_caption(texts, getattr(output, "boxes", None), scores, image.size)
            return OCRResult("uncertain" if uncertain else "ok", text, caption)
        except Exception:
            return OCRResult("failed")
