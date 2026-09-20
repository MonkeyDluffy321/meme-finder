from io import BytesIO
import unittest
from unittest.mock import MagicMock, patch

from PIL import Image

from utils.importer import ImportError
from utils.importer_url import download_image, download_resource
from utils.uploads import validate_upload, MAX_BYTES


class RedirectTests(unittest.TestCase):
    def setUp(self):
        buffer = BytesIO()
        Image.new("RGB", (120, 120), "red").save(buffer, format="PNG")
        self.content = buffer.getvalue()
        self.connections = []
        def connection(*args, **kwargs):
            mock = MagicMock()
            self.connections.append(mock)
            mock.getresponse.return_value = self.responses.pop(0)
            return mock
        self.responses = []
        for name in ("HTTPConnection", "HTTPSConnection"):
            patcher = patch("utils.importer_url." + name, side_effect=connection)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = patch("utils.importer_url.socket.getaddrinfo", return_value=self.address("93.184.216.34"))
        self.dns = patcher.start()
        self.addCleanup(patcher.stop)

    def address(self, ip):
        return [(2, 1, 6, "", (ip, 443))]

    def response(self, status=200, body=None, **headers):
        response = MagicMock()
        response.__enter__.return_value = response
        response.status = status
        headers.setdefault("Content-Type", "image/png")
        response.getheader.side_effect = lambda key, default=None: headers.get(key, default)
        response.read1.side_effect = [self.content if body is None else body, b""]
        self.responses.append(response)

    def test_safe_public_relative_and_absolute_redirects(self):
        self.response(302, Location="/second")
        self.response(307, Location="https://cdn.example.com/image.png")
        self.response()
        content = download_image("https://example.com/start")
        self.assertEqual(validate_upload(content).image.size, (120, 120))
        self.assertEqual([call.args[0] for call in self.dns.call_args_list],
                         ["example.com", "example.com", "cdn.example.com"])
        self.assertTrue(all(conn.close.called for conn in self.connections))

    def test_unsafe_redirect_addresses_blocked_before_connection(self):
        for address in ("127.0.0.1", "10.0.0.1", "169.254.169.254", "::1", "224.0.0.1", "240.0.0.1", "0.0.0.0"):
            with self.subTest(address=address):
                self.responses = []
                self.connections = []
                self.response(302, Location="http://localhost/image")
                self.dns.side_effect = [self.address("93.184.216.34"), self.address(address)]
                with self.assertRaisesRegex(ImportError, "public"):
                    download_image("https://example.com/start")
                self.assertEqual(len(self.connections), 1)

    def test_limit(self):
        for hop in range(4):
            self.response(302, Location=f"/hop{hop}")
        with self.assertRaisesRegex(ImportError, "limit"):
            download_image("https://example.com/start")
        self.assertEqual(len(self.connections), 4)

    def test_loop(self):
        self.response(302, Location="/start#fragment")
        with self.assertRaisesRegex(ImportError, "loop"):
            download_image("https://example.com/start")
        self.assertEqual(len(self.connections), 1)

    def test_direct(self):
        self.response()
        self.assertEqual(download_image("https://example.com/image"), self.content)
        self.assertEqual(len(self.connections), 1)

    def test_public_nat64_and_mixed_public_dns_allowed(self):
        self.dns.return_value = self.address("64:ff9b::6810:2865") + self.address("104.16.71.101")
        self.response()
        self.assertEqual(download_image("https://example.com/image"), self.content)
        with patch("utils.importer_url.socket.create_connection") as connect:
            self.connections[0]._create_connection(("example.com", 443))
            self.assertEqual(connect.call_args.args[0], ("64:ff9b::6810:2865", 443))

    def test_unsafe_nat64_embedded_ipv4_blocked(self):
        for address in ("64:ff9b::a00:1", "64:ff9b::7f00:1", "64:ff9b::a9fe:a9fe",
                        "64:ff9b::e000:1", "64:ff9b::", "64:ff9b::f000:1", "64:ff9b::6440:1"):
            with self.subTest(address=address):
                self.dns.return_value = self.address("104.16.40.101") + self.address(address)
                with self.assertRaisesRegex(ImportError, "public"):
                    download_image("https://example.com/image")
        self.assertEqual(self.connections, [])

    def test_other_reserved_ipv6_still_blocked(self):
        for address in ("100::1", "64:ff9b:1::6810:2865", "::6810:2865"):
            with self.subTest(address=address):
                self.dns.return_value = self.address(address)
                with self.assertRaisesRegex(ImportError, "public"):
                    download_image("https://example.com/image")
        self.assertEqual(self.connections, [])

    def test_redirect_revalidates_nat64_destination(self):
        self.response(302, Location="https://cdn.example.com/image")
        self.dns.side_effect = [self.address("64:ff9b::6810:2865"), self.address("64:ff9b::c0a8:1")]
        with self.assertRaisesRegex(ImportError, "public"):
            download_image("https://example.com/start")
        self.assertEqual(len(self.connections), 1)

    def test_unsupported_scheme(self):
        self.response(302, Location="file:///etc/passwd")
        with self.assertRaises(ImportError):
            download_image("https://example.com/start")
        self.assertEqual(len(self.connections), 1)

    def test_page_and_robots_redirects_still_rejected(self):
        for kind in ("text/html", "text/plain"):
            self.response(302, Location="https://example.com/other")
            with self.assertRaisesRegex(ImportError, "without redirects"):
                download_resource("https://example.com/start", content_types=(kind,))

    def test_final_type_and_size_enforced(self):
        for headers in ({"Content-Type": "text/html"}, {"Content-Length": str(MAX_BYTES + 1)}):
            self.response(302, Location="/final")
            self.response(**headers)
            with self.assertRaises(ImportError):
                download_image("https://example.com/start")

    def test_crawler_uses_real_safe_image_redirect_path(self):
        from utils.crawler import crawl
        self.response(body=b"User-agent: *\nAllow: /", **{"Content-Type": "text/plain"})
        self.response(body=b'<img src="https://i.imgflip.com/example.jpg">', **{"Content-Type": "text/html"})
        self.response(body=b"User-agent: *\nAllow: /", **{"Content-Type": "text/plain"})
        self.response(302, Location="/final.jpg")
        self.response()
        with patch("utils.crawler.read_index", return_value=[]), \
                patch("utils.crawler.suggest_metadata", return_value=({}, "test")), \
                patch("utils.crawler.sleep"):
            report = crawl(["https://example.com/page"], [])
        self.assertEqual(report["errors"], [])
        self.assertEqual(len(report["candidates"]), 1)
        paths = [conn.request.call_args.args[1] for conn in self.connections]
        self.assertEqual(paths, ["/robots.txt", "/page", "/robots.txt", "/example.jpg", "/final.jpg"])

    def test_crawler_identifies_image_host_robots_redirect(self):
        from utils.crawler import crawl
        self.response(body=b"User-agent: *\nAllow: /", **{"Content-Type": "text/plain"})
        self.response(body=b'<img src="https://i.imgflip.com/example.jpg">', **{"Content-Type": "text/html"})
        self.response(301, Location="https://example.com/robots.txt")
        with patch("utils.crawler.read_index", return_value=[]), patch("utils.crawler.sleep"):
            report = crawl(["https://example.com/page"], [])
        self.assertEqual(report["candidates"], [])
        self.assertIn("HTTP 301 at https://i.imgflip.com/robots.txt", report["errors"][0]["reason"])
        self.assertEqual(len(self.connections), 3)

    def test_http_failure_is_not_misreported_as_redirect(self):
        self.response(403)
        with self.assertRaisesRegex(ImportError, "HTTP 403 at https://example.com/image"):
            download_image("https://example.com/image")

    def test_crawler_reports_missing_image_host_robots(self):
        from utils.crawler import crawl
        self.response(body=b"User-agent: *\nAllow: /", **{"Content-Type": "text/plain"})
        self.response(body=b'<img src="https://i.imgflip.com/example.jpg">', **{"Content-Type": "text/html"})
        self.response(404)
        with patch("utils.crawler.read_index", return_value=[]), patch("utils.crawler.sleep"):
            report = crawl(["https://example.com/page"], [])
        self.assertEqual(report["candidates"], [])
        self.assertEqual(report["errors"][0]["reason"],
                         "Download failed: HTTP 404 at https://i.imgflip.com/robots.txt.")
        self.assertEqual(len(self.connections), 3)
