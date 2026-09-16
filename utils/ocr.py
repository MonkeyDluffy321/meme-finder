"""Optional local RapidOCR provider. Upload text is never globally cached."""

from dataclasses import dataclass
from pathlib import Path
from threading import RLock

_LOCK = RLock()
_ENGINE = None


@dataclass
class OCRResult:
    status: str
    text: str = ""


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
            return OCRResult("uncertain" if uncertain else "ok", text)
        except Exception:
            return OCRResult("failed")
