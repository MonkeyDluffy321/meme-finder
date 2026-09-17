"""Pure Pillow layout and in-memory export for creator drafts.

Uses Pillow's embedded scalable Aileron Regular via load_default(size=...).
No OS font lookup, downloads, user-content caches or file writes. Pillow ships
the font; we do not copy or redistribute a separate font asset.
Font provenance: PIL/ImageFont.py, load_default; Aileron by dot colon
(https://dotcolon.net/fonts/aileron). The embedded font's copyright name-table
records state "No Rights Reserved." No external font asset is required.

Wrapping collapses horizontal whitespace and preserves every explicit newline.
Oversized words split by code point; even an oversized glyph consumes a line.
Boxes clip horizontally to their requested width and vertically to the canvas.
Font size never changes to fit. RenderResult reports captions whose ink clips.
"""

from dataclasses import dataclass, field
from io import BytesIO
import math

from PIL import Image, ImageDraw, ImageFont, ImageOps

from utils.creator import Caption, CreatorDraft


class RenderingError(ValueError):
    """Safe rendering failure; callers must not offer a stale export."""


@dataclass(frozen=True)
class TextLine:
    text: str = field(repr=False)
    x: int
    y: int
    width: int
    height: int


@dataclass(frozen=True)
class CaptionLayout:
    caption_id: int
    clip_box: tuple[int, int, int, int]
    lines: tuple[TextLine, ...]
    overflow: bool


@dataclass(frozen=True)
class RenderResult:
    png: bytes = field(repr=False)
    width: int
    height: int
    overflow_caption_ids: tuple[int, ...]


def load_font(size):
    """Use the scalable font shipped by the existing Pillow dependency.

    A missing FreeType build is an explicit error, never a tiny bitmap fallback.
    The embedded font has limited character coverage (primarily Latin text).
    """
    try:
        font = ImageFont.load_default(size=size)
        if not isinstance(font, ImageFont.FreeTypeFont):
            raise RuntimeError("Scalable font unavailable")
        return font
    except Exception:
        raise RenderingError("The caption font is unavailable. Use Pillow with FreeType support.") from None


def _bbox(text, font, stroke):
    return font.getbbox(text, stroke_width=stroke)


def _ink_width(text, font, stroke):
    left, _, right, _ = _bbox(text, font, stroke)
    return right - left


def wrap_text(text, font, width, stroke=0):
    """Return bounded lines, retaining empty paragraphs, without text loss in words."""
    lines = []
    for paragraph in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        current = ""
        for word in paragraph.split():
            candidate = f"{current} {word}" if current else word
            if _ink_width(candidate, font, stroke) <= width:
                current = candidate
                continue
            if current:
                lines.append(current)
                current = ""
            for char in word:
                if current and _ink_width(current + char, font, stroke) > width:
                    lines.append(current)
                    current = ""
                current += char
        lines.append(current)
    return tuple(lines)


def layout_caption(caption: Caption, size, font=None):
    """Measure ink boxes in canvas pixels; layout itself never draws or scales."""
    font = load_font(caption.font_size) if font is None else font
    canvas_width, canvas_height = size
    x = math.floor(caption.x * canvas_width)
    y = math.floor(caption.y * canvas_height)
    box_width = max(1, math.floor(caption.width * canvas_width))
    right = min(canvas_width, x + box_width)
    clip_box = (x, y, right, canvas_height)
    ascent, descent = font.getmetrics()
    line_height = ascent + descent + 2 * caption.outline_width + max(1, caption.font_size // 5)
    lines = []
    overflow = False
    for index, text in enumerate(wrap_text(caption.text, font, box_width, caption.outline_width)):
        left, top, ink_right, bottom = _bbox(text, font, caption.outline_width)
        width, height = ink_right - left, bottom - top
        offset = {"left": 0, "center": (box_width - width) // 2,
                  "right": box_width - width}[caption.alignment]
        line_x, line_y = x + offset, y + index * line_height
        if text and (line_x < x or line_x + width > right
                     or line_y + height > canvas_height):
            overflow = True
        lines.append(TextLine(text, line_x, line_y, width, height))
    return CaptionLayout(caption.id, clip_box, tuple(lines), overflow)


def _draw_image_layer(canvas, layer):
    """Fit first, rotate the box about its center, then clip to the canvas.

    Contain padding is transparent. Source alpha follows shared upload policy
    (flattened on white); opacity applies to the whole fitted source. ImageOps.fit
    center-crops without allocating an enormous intermediate for extreme ratios.
    """
    if layer.opacity == 0:
        return
    width = max(1, math.floor(layer.width * canvas.width))
    height = max(1, math.floor(layer.height * canvas.height))
    x = math.floor(layer.x * canvas.width)
    y = math.floor(layer.y * canvas.height)
    with Image.open(BytesIO(layer.image_png)) as source:
        if layer.fit == "cover":
            tile = ImageOps.fit(source, (width, height), method=Image.Resampling.LANCZOS).convert("RGBA")
        else:
            scale = min(width / source.width, height / source.height)
            fitted = source.resize((max(1, round(source.width * scale)),
                                    max(1, round(source.height * scale))), Image.Resampling.LANCZOS)
            tile = Image.new("RGBA", (width, height))
            tile.paste(fitted, ((width - fitted.width) // 2, (height - fitted.height) // 2))
    if layer.rotation:
        tile = tile.rotate(layer.rotation, resample=Image.Resampling.BICUBIC, expand=True)
    x -= (tile.width - width) // 2
    y -= (tile.height - height) // 2
    if layer.opacity != 100:
        tile.putalpha(tile.getchannel("A").point([round(i * layer.opacity / 100) for i in range(256)]))
    left, top = max(0, x), max(0, y)
    right, bottom = min(canvas.width, x + tile.width), min(canvas.height, y + tile.height)
    if right > left and bottom > top:
        visible = tile.crop((left - x, top - y, right - x, bottom - y))
        canvas.paste(visible, (left, top), visible)


def render_draft(draft: CreatorDraft):
    """Render from pristine RGB pixels and return the exact preview/export PNG.

    Images paint in list order below all captions. Later captions paint over
    earlier ones. All metadata is discarded even for
    directly constructed drafts containing ancillary PNG chunks.
    """
    if not isinstance(draft, CreatorDraft):
        raise RenderingError("Choose a valid creator draft.")
    try:
        with Image.open(BytesIO(draft.base_png)) as source:
            source.load()
            canvas = Image.new("RGB", source.size)
            canvas.paste(source)
        for layer in draft.image_layers:
            _draw_image_layer(canvas, layer)
        overflow = []
        for caption in draft.captions:
            if not caption.text.strip():
                continue
            font = load_font(caption.font_size)
            layout = layout_caption(caption, canvas.size, font)
            if layout.overflow:
                overflow.append(caption.id)
            x, y, right, bottom = layout.clip_box
            if right <= x or bottom <= y:
                continue
            # Allocate only the visible region, never a text-sized unbounded image.
            layer = Image.new("RGBA", (right - x, bottom - y))
            draw = ImageDraw.Draw(layer)
            for line in layout.lines:
                if not line.text or line.y >= bottom:
                    continue
                left, top, _, _ = _bbox(line.text, font, caption.outline_width)
                draw.text((line.x - x - left, line.y - y - top), line.text, font=font,
                          fill=caption.fill_color, stroke_fill=caption.outline_color,
                          stroke_width=caption.outline_width)
            canvas.paste(layer, (x, y), layer)
        output = BytesIO()
        canvas.save(output, format="PNG")
        return RenderResult(output.getvalue(), canvas.width, canvas.height, tuple(overflow))
    except RenderingError:
        raise
    except Exception:
        raise RenderingError("This meme could not be rendered. Check the image and caption settings.") from None


def export_png(draft: CreatorDraft):
    return render_draft(draft).png


def export_jpg(draft: CreatorDraft):
    """Encode the same composition as lossy RGB JPEG, quality 95, no metadata."""
    result = render_draft(draft)
    try:
        with Image.open(BytesIO(result.png)) as image:
            output = BytesIO()
            image.save(output, format="JPEG", quality=95, subsampling=0)
            return output.getvalue()
    except Exception:
        raise RenderingError("This meme could not be exported as JPG.") from None
