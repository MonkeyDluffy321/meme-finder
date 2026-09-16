from io import BytesIO
import unittest
from unittest.mock import patch
from PIL import Image

from utils.uploads import validate_upload, UploadError


def image_bytes(fmt="PNG", size=(40, 30), mode="RGB"):
    buffer = BytesIO()
    Image.new(mode, size, "red").save(buffer, format=fmt)
    return buffer.getvalue()


class UploadTests(unittest.TestCase):
    def test_supported_formats(self):
        for fmt in ("PNG", "JPEG", "WEBP"):
            with self.subTest(fmt=fmt):
                upload = validate_upload(image_bytes(fmt))
                self.assertEqual(upload.image.mode, "RGB")
                self.assertEqual(upload.image.size, (40, 30))
                self.assertTrue(upload.preview.startswith(b"\x89PNG"))

    def test_invalid_content_and_unsupported_format(self):
        for content in (b"", b"fake.jpg", b"<svg></svg>", image_bytes("GIF"), image_bytes("BMP")):
            with self.assertRaises(UploadError):
                validate_upload(content)

    def test_byte_limit(self):
        with patch("utils.uploads.MAX_BYTES", 10), self.assertRaises(UploadError):
            validate_upload(image_bytes())

    def test_pixel_limit(self):
        with patch("utils.uploads.MAX_PIXELS", 10), self.assertRaises(UploadError):
            validate_upload(image_bytes())

    def test_animated_png_rejected(self):
        buffer = BytesIO()
        Image.new("RGB", (20, 20), "red").save(buffer, format="PNG", save_all=True,
            append_images=[Image.new("RGB", (20, 20), "blue")], duration=100)
        with self.assertRaises(UploadError):
            validate_upload(buffer.getvalue())

    def test_transparency_composited_and_metadata_removed(self):
        image = Image.new("RGBA", (20, 20), (0, 0, 0, 0))
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        upload = validate_upload(buffer.getvalue())
        self.assertEqual(upload.image.getpixel((0, 0)), (255, 255, 255))
        self.assertEqual(upload.image.info, {})

    def test_orientation_and_size_normalized(self):
        image = Image.new("RGB", (2000, 1000), "red")
        exif = Image.Exif()
        exif[274] = 6
        buffer = BytesIO()
        image.save(buffer, format="JPEG", exif=exif)
        upload = validate_upload(buffer.getvalue())
        self.assertEqual(upload.image.size, (800, 1600))
        self.assertFalse(upload.image.getexif())

    def test_digest_changes_with_upload(self):
        self.assertNotEqual(validate_upload(image_bytes()).digest,
                            validate_upload(image_bytes(size=(30, 40))).digest)
