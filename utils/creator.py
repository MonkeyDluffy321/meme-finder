"""Immutable, session-agnostic meme drafts. No I/O, accounts or UI dependencies.

Positions are fractions of the normalized canvas; x/y mark the box's top-left.
Width controls wrapping, not scaling. Caption order is paint order. Operations
return a new draft and never modify a caller's existing draft.
"""

from dataclasses import dataclass, field, replace
from hashlib import sha256
from io import BytesIO
import math
import re
import warnings

from PIL import Image

from utils.uploads import MAX_SIDE, UploadError, validate_upload

MAX_CAPTIONS = 10
MAX_IMAGE_LAYERS = 8
MAX_TEXT_LENGTH = 500
MIN_FONT_SIZE = 8
MAX_FONT_SIZE = 200
MAX_OUTLINE_WIDTH = 12
MAX_NORMALIZED_BYTES = MAX_SIDE * MAX_SIDE * 4 + 65536


class CreatorError(ValueError):
    """A safe, actionable validation message for callers to display."""


def _integer(value, minimum, maximum, label):
    if type(value) is not int or not minimum <= value <= maximum:
        raise CreatorError(f"{label} must be an integer from {minimum} to {maximum}.")


@dataclass(frozen=True)
class Caption:
    id: int
    text: str = field(default="", repr=False)
    x: float = 0.05
    y: float = 0.05
    width: float = 0.9
    font_size: int = 40
    alignment: str = "center"
    fill_color: str = "#FFFFFF"
    outline_color: str = "#000000"
    outline_width: int = 2

    def __post_init__(self):
        if type(self.id) is not int or self.id < 1:
            raise CreatorError("Caption IDs must be positive integers.")
        if not isinstance(self.text, str) or len(self.text) > MAX_TEXT_LENGTH:
            raise CreatorError(f"Captions must contain at most {MAX_TEXT_LENGTH} characters.")
        # Keep line breaks and tabs; reject control characters and lone surrogates.
        if any((ord(c) < 32 and c not in "\n\r\t") or 127 <= ord(c) < 160
               or 0xD800 <= ord(c) <= 0xDFFF for c in self.text):
            raise CreatorError("Caption contains unsupported control characters.")
        for name in ("x", "y", "width"):
            value = getattr(self, name)
            if (type(value) not in (int, float) or not math.isfinite(value)
                    or not 0 <= value <= 1 or (name == "width" and value == 0)):
                raise CreatorError("Position must be between 0 and 1; width must be greater than 0 and at most 1.")
        _integer(self.font_size, MIN_FONT_SIZE, MAX_FONT_SIZE, "Font size")
        _integer(self.outline_width, 0, MAX_OUTLINE_WIDTH, "Outline width")
        if self.alignment not in ("left", "center", "right"):
            raise CreatorError("Choose left, center or right alignment.")
        for color in (self.fill_color, self.outline_color):
            if not isinstance(color, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
                raise CreatorError("Colors must use six-digit #RRGGBB notation.")


def _source_size(content):
    """Verify the model boundary, including drafts constructed without from_bytes."""
    if not isinstance(content, bytes) or not 0 < len(content) <= MAX_NORMALIZED_BYTES:
        raise CreatorError("Choose a valid normalized image.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            return _verified_size(content)
    except CreatorError:
        raise
    except Exception:
        raise CreatorError("The draft image could not be decoded safely.") from None


def _verified_size(content):
    with Image.open(BytesIO(content)) as image:
        if (image.format != "PNG" or image.mode != "RGB"
                or getattr(image, "n_frames", 1) != 1
                or not all(1 <= side <= MAX_SIDE for side in image.size)):
            raise CreatorError("The draft source must be a static RGB PNG up to 1600 pixels per side.")
        size = image.size
        image.verify()
        return size


@dataclass(frozen=True)
class ImageLayer:
    """Normalized RGB overlay. Positive rotation is counterclockwise about its box center.

    x/y may be negative to place a layer partially outside the canvas. Dimensions
    are bounded to one canvas; contain leaves empty space, cover center-crops.
    Original filenames, paths and arbitrary source metadata are not retained.
    """

    id: int
    image_png: bytes = field(repr=False)
    source_label: str = field(default="Uploaded image", repr=False)
    x: float = 0.1
    y: float = 0.1
    width: float = 0.3
    height: float = 0.3
    rotation: float = 0.0
    fit: str = "contain"
    opacity: int = 100
    digest: str = field(init=False)

    def __post_init__(self):
        if type(self.id) is not int or self.id < 1:
            raise CreatorError("Image IDs must be positive integers.")
        label = self.source_label
        if (not isinstance(label, str) or not label.strip() or len(label) > 200
                or any(ord(c) < 32 or 127 <= ord(c) < 160 or c in "/\\:" for c in label)):
            raise CreatorError("Use a short display label without paths or control characters.")
        for name, low, high in (("x", -1, 1), ("y", -1, 1), ("width", 0, 1),
                                ("height", 0, 1), ("rotation", -180, 180)):
            value = getattr(self, name)
            if (type(value) not in (int, float) or not math.isfinite(value)
                    or not low <= value <= high or (name in ("width", "height") and value == 0)):
                raise CreatorError("Image position must be -1 to 1, size greater than 0 and at most 1, and rotation -180 to 180.")
        if self.fit not in ("contain", "cover"):
            raise CreatorError("Choose contain or cover for the image fit.")
        _integer(self.opacity, 0, 100, "Opacity")
        if not isinstance(self.image_png, bytes):
            raise CreatorError("Choose valid image bytes.")
        try:
            normalized = validate_upload(self.image_png).preview
        except UploadError as error:
            raise CreatorError(str(error)) from None
        object.__setattr__(self, "image_png", normalized)
        object.__setattr__(self, "digest", sha256(normalized).hexdigest())


@dataclass(frozen=True)
class CreatorDraft:
    base_png: bytes = field(repr=False)
    source_kind: str = "upload"
    source_label: str = field(default="Uploaded image", repr=False)
    template_id: str | None = None
    captions: tuple[Caption, ...] = field(default_factory=lambda: (Caption(1),))
    next_caption_id: int = 2
    revision: int = 0
    image_layers: tuple[ImageLayer, ...] = ()
    next_image_id: int = 1
    digest: str = field(init=False)
    width: int = field(init=False)
    height: int = field(init=False)

    def __post_init__(self):
        if (not isinstance(self.image_layers, tuple)
                or any(not isinstance(layer, ImageLayer) for layer in self.image_layers)):
            raise CreatorError("Image layers must be a tuple of ImageLayer objects.")
        if len(self.image_layers) > MAX_IMAGE_LAYERS:
            raise CreatorError(f"Use at most {MAX_IMAGE_LAYERS} image layers.")
        image_ids = [layer.id for layer in self.image_layers]
        if len(set(image_ids)) != len(image_ids):
            raise CreatorError("Image IDs must be unique.")
        if type(self.next_image_id) is not int or self.next_image_id <= max(image_ids, default=0):
            raise CreatorError("The next image ID must exceed all existing image IDs.")
        if self.source_kind not in ("template", "upload"):
            raise CreatorError("Source must be a template or upload.")
        if (not isinstance(self.source_label, str) or not self.source_label.strip()
                or len(self.source_label) > 200
                or any(ord(c) < 32 or ord(c) == 127 for c in self.source_label)):
            raise CreatorError("Use a source label of 1 to 200 printable characters.")
        if self.source_kind == "template":
            if not isinstance(self.template_id, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,100}", self.template_id):
                raise CreatorError("A template source needs a valid template ID.")
        elif self.template_id is not None:
            raise CreatorError("Uploaded sources do not have a template ID.")
        if not isinstance(self.captions, tuple) or any(not isinstance(c, Caption) for c in self.captions):
            raise CreatorError("Captions must be a tuple of Caption objects.")
        if len(self.captions) > MAX_CAPTIONS:
            raise CreatorError(f"Use at most {MAX_CAPTIONS} captions.")
        ids = [c.id for c in self.captions]
        if len(set(ids)) != len(ids):
            raise CreatorError("Caption IDs must be unique.")
        if type(self.next_caption_id) is not int or self.next_caption_id <= max(ids, default=0):
            raise CreatorError("The next caption ID must exceed all existing IDs.")
        if type(self.revision) is not int or self.revision < 0:
            raise CreatorError("Draft revision must be a nonnegative integer.")
        width, height = _source_size(self.base_png)
        object.__setattr__(self, "width", width)
        object.__setattr__(self, "height", height)
        object.__setattr__(self, "digest", sha256(self.base_png).hexdigest())

    @classmethod
    def from_bytes(cls, content, *, source_kind="upload", source_label="Uploaded image", template_id=None):
        """Normalize untrusted upload or fetched template bytes without network I/O."""
        try:
            upload = validate_upload(content)
        except UploadError as error:
            raise CreatorError(str(error)) from None
        return cls(upload.preview, source_kind, source_label, template_id)

    def add_caption(self, **settings):
        if len(self.captions) >= MAX_CAPTIONS:
            raise CreatorError(f"Use at most {MAX_CAPTIONS} captions.")
        _check_settings(settings)
        caption = Caption(self.next_caption_id, **settings)
        return replace(self, captions=(*self.captions, caption),
                       next_caption_id=self.next_caption_id + 1, revision=self.revision + 1)

    def remove_caption(self, caption_id):
        self._find_caption(caption_id)
        return replace(self, captions=tuple(c for c in self.captions if c.id != caption_id),
                       revision=self.revision + 1)

    def update_caption(self, caption_id, **settings):
        caption = self._find_caption(caption_id)
        _check_settings(settings)
        updated = replace(caption, **settings)
        return replace(self, captions=tuple(updated if c.id == caption_id else c for c in self.captions),
                       revision=self.revision + 1)

    def _find_caption(self, caption_id):
        if type(caption_id) is int:
            for caption in self.captions:
                if caption.id == caption_id:
                    return caption
        raise CreatorError("That caption no longer exists.")

    def add_image_layer(self, content, **settings):
        if len(self.image_layers) >= MAX_IMAGE_LAYERS:
            raise CreatorError(f"Use at most {MAX_IMAGE_LAYERS} image layers.")
        _check_image_settings(settings)
        layer = ImageLayer(self.next_image_id, content, **settings)
        return replace(self, image_layers=(*self.image_layers, layer),
                       next_image_id=self.next_image_id + 1, revision=self.revision + 1)

    def update_image_layer(self, layer_id, **settings):
        layer = self._find_image(layer_id)
        _check_image_settings(settings)
        return self._replace_image(replace(layer, **settings))

    def replace_image_layer(self, layer_id, content, *, source_label=None):
        layer = self._find_image(layer_id)
        return self._replace_image(replace(layer, image_png=content,
            source_label=layer.source_label if source_label is None else source_label))

    def remove_image_layer(self, layer_id):
        self._find_image(layer_id)
        return replace(self, image_layers=tuple(layer for layer in self.image_layers if layer.id != layer_id),
                       revision=self.revision + 1)

    def _find_image(self, layer_id):
        if type(layer_id) is int:
            for layer in self.image_layers:
                if layer.id == layer_id:
                    return layer
        raise CreatorError("That image layer no longer exists.")

    def _replace_image(self, updated):
        return replace(self, image_layers=tuple(updated if layer.id == updated.id else layer
                                                for layer in self.image_layers), revision=self.revision + 1)


def _check_image_settings(settings):
    allowed = {"source_label", "x", "y", "width", "height", "rotation", "fit", "opacity"}
    if any(name not in allowed for name in settings):
        raise CreatorError("Unknown image setting. Use replace_image_layer to change the source.")


def _check_settings(settings):
    if any(name not in Caption.__dataclass_fields__ or name == "id" for name in settings):
        raise CreatorError("Unknown caption setting or attempted ID change.")
