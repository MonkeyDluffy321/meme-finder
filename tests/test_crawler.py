from copy import deepcopy
from io import BytesIO
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from PIL import Image

from utils.crawler import crawl, extract_images, normalize_url
from utils.importer import ImportError
from utils.importer_url import download_resource


class DiscoveryTests(unittest.TestCase):
    def test_relative_absolute_and_duplicate_urls(self):
        html = '<img src="../a.jpg"><img src="https://example.com/a.jpg#x"><img src="//cdn.example.com/b.png">'
        self.assertEqual(extract_images(html, "https://example.com/posts/page"),
                         ["https://example.com/a.jpg", "https://cdn.example.com/b.png"])

    def test_unsupported_and_tiny_images(self):
        html = ''.join(f'<img src="{src}">' for src in ("data:image/png;base64,x", "file:///x", "javascript:x"))
        html += '<img src="/pixel.gif"><img src="/avatar.jpg"><img src="/a.png" width="1">'
        html += '<img src="/b.png" height="50px"><img src="/meme.png" width="400">'
        self.assertEqual(extract_images(html, "https://example.com"), ["https://example.com/meme.png"])
        self.assertIsNone(normalize_url("https://user:pass@example.com"))

    def test_meta_robots_and_limit(self):
        html = '<img src="/a"><img src="/b">'
        self.assertEqual(len(extract_images(html, "https://example.com", 1)), 1)
        self.assertEqual(extract_images(html + '<meta name="robots" content="noimageindex">',
                                       "https://example.com"), [])


class TransportTests(unittest.TestCase):
    def test_private_addresses_rejected_by_shared_transport(self):
        for address in ("127.0.0.1", "10.0.0.1", "169.254.169.254", "::1"):
            with self.subTest(address=address), \
                    patch("utils.importer_url.socket.getaddrinfo", return_value=[
                        (socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 443))]), \
                    patch("utils.importer_url.HTTPSConnection") as connect:
                report = crawl(["https://example.com"], [], delay=0)
                self.assertIn("public", report["errors"][0]["reason"])
                connect.assert_not_called()

    def test_html_content_type_size_and_indexing_headers(self):
        response = MagicMock()
        response.__enter__.return_value = response
        response.status = 200
        headers = {"Content-Type": "text/html; charset=utf-8"}
        response.getheader.side_effect = lambda key, default=None: headers.get(key, default)
        response.read1.side_effect = [b"<html></html>", b""]
        connection = MagicMock()
        connection.getresponse.return_value = response
        with patch("utils.importer_url.socket.getaddrinfo", return_value=[
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]), \
                patch("utils.importer_url.HTTPSConnection", return_value=connection):
            self.assertEqual(download_resource("https://example.com", content_types=("text/html",)), b"<html></html>")
            headers["Content-Type"] = "image/png"
            with self.assertRaisesRegex(ImportError, "content type"):
                download_resource("https://example.com", content_types=("text/html",))
            headers["Content-Type"] = "text/html"
            headers["Content-Length"] = "100"
            with self.assertRaisesRegex(ImportError, "limit"):
                download_resource("https://example.com", content_types=("text/html",), max_bytes=10)
            headers["X-Robots-Tag"] = "noindex"
            with self.assertRaisesRegex(ImportError, "disallows"):
                download_resource("https://example.com", content_types=("text/html",), respect_indexing=True)


class PipelineTests(unittest.TestCase):
    def setUp(self):
        buffer = BytesIO()
        Image.effect_noise((200, 200), 70).convert("RGB").save(buffer, format="PNG")
        self.image = buffer.getvalue()
        self.html = b'<img src="/a.png"><img src="/b.png">'
        self.rules = b"User-agent: *\nAllow: /\n"
        self.metadata = dict(name="Meme", meaning="A work reaction", keywords=["work", "work"],
                             situations=["working"], categories=["work"], emotions=["joy"], aliases=[])
        self.patches = [patch("utils.crawler.download_resource", side_effect=self.fetch),
                        patch("utils.crawler.download_image", return_value=self.image),
                        patch("utils.crawler.suggest_metadata", return_value=(self.metadata, "ok")),
                        patch("utils.crawler.read_index", return_value=[]),
                        patch("utils.crawler.sleep")]
        self.fetch_mock, self.image_mock, self.analyzer, self.index, self.sleep = [p.start() for p in self.patches]
        for p in self.patches:
            self.addCleanup(p.stop)

    def fetch(self, url, **kwargs):
        return self.rules if url.endswith("/robots.txt") else self.html

    def test_analyzer_duplicates_and_no_mutation(self):
        memes = [{"id": "existing", "meaning": "untouched"}]
        before = deepcopy(memes)
        provider = object()
        with patch.object(Path, "write_text", side_effect=AssertionError("write")), \
                patch.object(Path, "write_bytes", side_effect=AssertionError("write")):
            report = crawl(["https://example.com/page"], memes, provider=provider, delay=0)
        self.assertEqual(memes, before)
        self.assertEqual(len(report["candidates"]), 1)
        self.assertEqual(report["candidates"][0]["keywords"], ["work"])
        self.assertEqual(report["candidates"][0]["description"], "A work reaction")
        self.assertEqual(report["skipped"][0]["duplicate_status"], "duplicate")
        self.analyzer.assert_called_once_with(self.image, memes, provider=provider)

    def test_existing_local_catalog_duplicate(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "existing.png").write_bytes(self.image)
            with patch("utils.crawler.LOCAL_IMAGES", Path(directory)):
                report = crawl(["https://example.com"], [{"id": "existing", "local_image": "existing.png"}], delay=0)
        self.assertFalse(report["candidates"])
        self.assertEqual(report["skipped"][0]["duplicate_of"], "existing")
        self.analyzer.assert_not_called()

    def test_near_duplicate_existing_hash(self):
        from utils.template_index import image_hash
        from utils.uploads import validate_upload
        fingerprint = image_hash(validate_upload(self.image).image)
        self.index.return_value = [{"id": "known", "hash": ("0" if fingerprint[0] == "1" else "1") + fingerprint[1:]}]
        report = crawl(["https://example.com"], [], delay=0)
        self.assertFalse(report["candidates"])
        self.assertEqual(report["skipped"][0]["duplicate_of"], "known")

    def test_robots_disallow_and_failure_are_closed(self):
        self.rules = b"User-agent: *\nDisallow: /\n"
        self.assertFalse(crawl(["https://example.com"], [], delay=0)["candidates"])
        self.image_mock.assert_not_called()
        self.fetch_mock.side_effect = ImportError("robots unavailable")
        report = crawl(["https://example.com"], [], delay=0)
        self.assertTrue(report["errors"])
        self.image_mock.assert_not_called()

    def test_limits_do_not_follow_links(self):
        self.html += b'<a href="/next">Next</a>'
        crawl(["https://example.com/page", "https://another.example/page"], [],
              max_pages=1, images_per_page=1, max_images=1, delay=0)
        self.assertEqual(self.image_mock.call_count, 1)
        self.assertEqual([call.args[0] for call in self.fetch_mock.call_args_list],
                         ["https://example.com/robots.txt", "https://example.com/page"])

    def test_failed_analysis_is_reported_without_candidates(self):
        self.analyzer.side_effect = RuntimeError("analysis failed")
        report = crawl(["https://example.com"], [], delay=0)
        self.assertFalse(report["candidates"])
        self.assertEqual(len(report["errors"]), 2)
