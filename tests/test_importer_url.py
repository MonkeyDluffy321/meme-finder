from io import BytesIO
import json
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from PIL import Image
from streamlit.testing.v1 import AppTest

from utils.importer import ImportError
from utils.importer_url import download_image, import_meme_url
from utils.uploads import MAX_BYTES


class URLImporterTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        (self.root / "memes.json").write_text("[]")
        self.metadata = dict(name="Remote Meme", meaning="Testing remote import", keywords="remote",
                             situations="testing", emotions="joy", categories="work")
        buffer = BytesIO()
        Image.new("RGB", (12, 12), "red").save(buffer, format="JPEG")
        self.content = buffer.getvalue()
        self.response = MagicMock()
        self.response.__enter__.return_value = self.response
        self.response.status = 200
        self.headers = {"Content-Type": "image/jpeg"}
        self.response.getheader.side_effect = lambda key, default=None: self.headers.get(key, default)
        self.response.read1.side_effect = [self.content, b""]
        self.connection = MagicMock()
        self.connection.getresponse.return_value = self.response
        for name in ("HTTPConnection", "HTTPSConnection"):
            patcher = patch("utils.importer_url." + name, return_value=self.connection)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = patch("utils.importer_url.socket.getaddrinfo", return_value=[
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))])
        self.dns = patcher.start()
        self.addCleanup(patcher.stop)

    def save(self, url="https://example.com/../../untrusted.exe"):
        return import_meme_url(self.metadata, url, data_dir=self.root)

    def test_success_and_pinned_address(self):
        record = self.save()
        self.assertRegex(record["local_image"], r"^remote-meme-[a-f0-9]+\.png$")
        with Image.open(self.root / "imported_images" / record["local_image"]) as image:
            self.assertEqual(image.format, "PNG")
        self.assertEqual(json.loads((self.root / "imported_memes.json").read_text()), [record])
        with patch("utils.importer_url.socket.create_connection") as connect:
            self.connection._create_connection(("example.com", 443))
            self.assertEqual(connect.call_args.args[0], ("93.184.216.34", 443))
        self.connection.close.assert_called()

    def test_http_supported(self):
        self.assertEqual(download_image("http://example.com/image"), self.content)

    def test_invalid_urls(self):
        for url in ("", "file:///tmp/a", "ftp://example.com/a", "https:///a", "https://x:bad/a",
                    "https://user:pass@example.com/a", "https://example.com/\r\na", "https://x\\y/a"):
            with self.subTest(url=url), self.assertRaises(ImportError):
                self.save(url)
        self.connection.request.assert_not_called()
        self.assertFalse((self.root / "imported_memes.json").exists())

    def test_private_and_mixed_dns_rejected(self):
        for address in ("127.0.0.1", "10.0.0.1", "169.254.169.254", "::1", "::ffff:127.0.0.1"):
            self.dns.return_value = [(2, 1, 6, "", ("93.184.216.34", 443)),
                                     (2, 1, 6, "", (address, 443))]
            with self.subTest(address=address), self.assertRaisesRegex(ImportError, "public"):
                self.save()
        self.connection.request.assert_not_called()

    def test_non_image_and_redirect_rejected(self):
        for content_type in ("text/html", "application/octet-stream", ""):
            self.headers["Content-Type"] = content_type
            with self.assertRaisesRegex(ImportError, "content type"):
                self.save()
        self.response.status = 302
        with self.assertRaisesRegex(ImportError, "without redirects"):
            self.save()
        self.response.read1.assert_not_called()

    def test_oversized_header_and_stream(self):
        self.headers["Content-Length"] = str(MAX_BYTES + 1)
        with self.assertRaisesRegex(ImportError, "10 MB"):
            self.save()
        self.response.read1.assert_not_called()
        del self.headers["Content-Length"]
        self.response.read1.side_effect = BytesIO(b"x" * (MAX_BYTES + 1)).read1
        with self.assertRaisesRegex(ImportError, "10 MB"):
            self.save()
        self.assertFalse((self.root / "imported_memes.json").exists())

    def test_network_failure_and_timeout(self):
        for error in (OSError("offline"), TimeoutError()):
            self.connection.getresponse.side_effect = error
            with self.assertRaisesRegex(ImportError, "Could not download"):
                self.save()
        self.assertFalse((self.root / "imported_images").exists())
        self.connection.close.assert_called()

    def test_transfer_deadline(self):
        with patch("utils.importer_url.monotonic", side_effect=[0, 1, 6]):
            with self.assertRaisesRegex(ImportError, "Could not download"):
                self.save()

    def test_corrupt_image_and_incomplete_response(self):
        self.response.read1.side_effect = [b"not an image", b""]
        with self.assertRaisesRegex(ImportError, "decoded safely"):
            self.save()
        self.headers["Content-Length"] = "100"
        self.response.read1.side_effect = [b"short", b""]
        with self.assertRaisesRegex(ImportError, "incomplete"):
            self.save()
        self.assertFalse((self.root / "imported_images").exists())

    def test_duplicate_and_rollback(self):
        self.save()
        target = self.root / "imported_memes.json"
        before = target.read_bytes()
        self.response.read1.side_effect = [self.content, b""]
        with self.assertRaisesRegex(ImportError, "already exists"):
            self.save()
        self.metadata["name"] = "Another Remote Meme"
        self.response.read1.side_effect = [self.content, b""]
        with patch("utils.importer.os.replace", side_effect=OSError("disk full")):
            with self.assertRaisesRegex(ImportError, "Could not save"):
                self.save()
        self.assertEqual(target.read_bytes(), before)
        self.assertEqual(len(list((self.root / "imported_images").iterdir())), 1)
        self.assertFalse(list(self.root.glob(".import-*")))

    @patch("utils.images.load_preview", return_value=None)
    def test_ui_url_submission(self, preview):
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py")).run()
        app.button(key="import_meme").click().run()
        app.text_input(key="importer_url").set_value("https://example.com/image")
        with patch("utils.importer_ui.import_meme_url", return_value={"name": "Remote Meme"}) as save:
            app.button(key="import_meme").click()
            next(b for b in app.button if b.label == "Import").click().run()
            self.assertEqual(save.call_args.args[1], "https://example.com/image")
        self.assertFalse(app.exception)
        self.assertTrue(any("Imported Remote Meme" in item.value for item in app.success))
