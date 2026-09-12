from email.message import Message
from urllib.error import HTTPError, URLError
import unittest
from unittest.mock import MagicMock, patch

from utils.images import MAX_IMAGE_BYTES, load_preview


class ImageTests(unittest.TestCase):
    def setUp(self):
        load_preview.clear()
        self.addCleanup(load_preview.clear)

    def response(self, content, content_type="image/png"):
        response = MagicMock()
        response.__enter__.return_value = response
        response.headers = Message()
        response.headers["Content-Type"] = content_type
        response.read.return_value = content
        return response

    @patch("utils.images.urlopen")
    def test_success_is_cached_in_memory(self, open_url):
        open_url.return_value = self.response(b"image bytes")
        for _ in range(2):
            self.assertEqual(load_preview("https://example.com/image.png"), b"image bytes")
        open_url.assert_called_once()
        self.assertEqual(open_url.call_args.kwargs["timeout"], 3)
        open_url.return_value.read.assert_called_once_with(MAX_IMAGE_BYTES + 1)

    @patch("utils.images.urlopen")
    def test_network_failures(self, open_url):
        for error in [TimeoutError(), URLError("offline"),
                      HTTPError("https://example.com/image", 404, "Not found", {}, None)]:
            with self.subTest(error=type(error).__name__):
                load_preview.clear()
                open_url.side_effect = error
                self.assertIsNone(load_preview("https://example.com/image"))

    @patch("utils.images.urlopen")
    def test_failure_is_cached(self, open_url):
        open_url.side_effect = URLError("offline")
        self.assertIsNone(load_preview("https://example.com/image"))
        self.assertIsNone(load_preview("https://example.com/image"))
        open_url.assert_called_once()

    @patch("utils.images.urlopen")
    def test_non_image_and_empty_or_oversized_responses(self, open_url):
        for content, content_type in [(b"<html>error</html>", "text/html"),
                                      (b"", "image/png"),
                                      (b"x" * (MAX_IMAGE_BYTES + 1), "image/png")]:
            with self.subTest(content_type=content_type, size=len(content)):
                load_preview.clear()
                open_url.return_value = self.response(content, content_type)
                self.assertIsNone(load_preview("https://example.com/image"))

    @patch("utils.images.urlopen")
    def test_missing_or_unsupported_urls(self, open_url):
        for url in [None, "", "file:///image.png", "data:image/png;base64,invalid"]:
            self.assertIsNone(load_preview(url))
        open_url.assert_not_called()


if __name__ == "__main__":
    unittest.main()
