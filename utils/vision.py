"""Generic explanation results and optional provider interface."""

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class Explanation:
    observations: str
    expression: str
    why_it_works: str
    wording: list[str]
    uncertainty: str


@dataclass
class VisionResult:
    status: str
    explanation: Explanation | None = field(default=None, repr=False)
    message: str = ""


class VisionProvider(Protocol):
    def explain(self, image_bytes: bytes, ocr_text: str = "",
                corrected_text: str | None = None, template_hint: dict | None = None) -> VisionResult:
        ...
