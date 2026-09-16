"""Decode untrusted uploads into bounded, metadata-free RGB images."""

from dataclasses import dataclass, field
from hashlib import sha256
from io import BytesIO
import warnings

from PIL import Image, ImageOps

MAX_BYTES = 10 * 1024 * 1024
MAX_PIXELS = 20_000_000
MAX_SIDE = 1600


class UploadError(ValueError):
    """Safe message suitable for the upload interface."""


@dataclass
class Upload:
    image: Image.Image = field(repr=False)
    preview: bytes = field(repr=False)
    digest: str


def validate_upload(content):
    if not content or len(content) > MAX_BYTES:
        raise UploadError("Choose an image up to 10 MB.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(content)) as source:
                if source.format not in {"JPEG", "PNG", "WEBP"}:
                    raise UploadError("Use JPEG, PNG or static WebP.")
                if getattr(source, "n_frames", 1) != 1:
                    raise UploadError("Animated images are not supported.")
                if source.width * source.height > MAX_PIXELS:
                    raise UploadError("Choose an image with at most 20 megapixels.")
                source.verify()
            with Image.open(BytesIO(content)) as source:
                oriented = ImageOps.exif_transpose(source)
                oriented.thumbnail((MAX_SIDE, MAX_SIDE), Image.Resampling.LANCZOS)
                rgba = oriented.convert("RGBA")
                clean = Image.new("RGB", rgba.size, "white")
                clean.paste(rgba, mask=rgba.getchannel("A"))
        buffer = BytesIO()
        clean.save(buffer, format="PNG")
        return Upload(clean, buffer.getvalue(), sha256(content).hexdigest())
    except UploadError:
        raise
    except Exception:
        raise UploadError("This image could not be decoded safely. Try another image.") from None
