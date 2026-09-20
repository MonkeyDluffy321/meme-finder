"""Bounded direct-image downloads; no redirects, proxies, or private networks."""

from http.client import HTTPConnection, HTTPSConnection, HTTPException
from ipaddress import ip_address
import socket
from time import monotonic
from urllib.parse import urlsplit

from utils.importer import ImportError, import_meme
from utils.uploads import MAX_BYTES


TIMEOUT = 5


def download_image(url):
    connection = None
    try:
        if not isinstance(url, str) or any(ord(c) <= 32 or ord(c) == 127 for c in url):
            raise ImportError("Enter a valid HTTP or HTTPS image URL.")
        parsed = urlsplit(url)
        if (parsed.scheme not in {"http", "https"} or not parsed.hostname
                or parsed.username is not None or parsed.password is not None
                or "\\" in url or "%" in parsed.hostname):
            raise ImportError("Enter a valid HTTP or HTTPS image URL without credentials.")
        host = parsed.hostname.encode("idna").decode("ascii")
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        if not addresses or any(not ip_address(item[4][0]).is_global for item in addresses):
            raise ImportError("Image URLs must point to a public internet address.")
        # Pin the validated IP, while retaining the hostname for Host and TLS
        # certificate verification. A second DNS lookup cannot change the target.
        address = addresses[0][4][0]
        deadline = monotonic() + TIMEOUT
        connection_type = HTTPSConnection if parsed.scheme == "https" else HTTPConnection
        connection = connection_type(host, port, timeout=TIMEOUT)
        connection._create_connection = lambda *args, **kwargs: socket.create_connection(
            (address, port), timeout=max(0.001, deadline - monotonic()))
        connection.connect()
        transport = connection.sock
        transport.settimeout(max(0.001, deadline - monotonic()))
        connection.request("GET", (parsed.path or "/") + ("?" + parsed.query if parsed.query else ""),
                           headers={"User-Agent": "MemeFinder/1.0", "Accept": "image/*",
                                    "Accept-Encoding": "identity"})
        with connection.getresponse() as response:
            if response.status != 200:
                raise ImportError("Image download failed. Use a direct image URL without redirects.")
            if not response.getheader("Content-Type", "").lower().startswith("image/"):
                raise ImportError("The URL must return an image content type.")
            length = response.getheader("Content-Length")
            if length is not None and (int(length) < 0 or int(length) > MAX_BYTES):
                raise ImportError("Choose an image up to 10 MB.")
            content = bytearray()
            while len(content) <= MAX_BYTES:
                remaining = deadline - monotonic()
                if remaining <= 0:
                    raise TimeoutError
                transport.settimeout(remaining)
                chunk = response.read1(min(64 * 1024, MAX_BYTES + 1 - len(content)))
                if not chunk:
                    break
                content.extend(chunk)
            if len(content) > MAX_BYTES:
                raise ImportError("Choose an image up to 10 MB.")
            if length is not None and len(content) != int(length):
                raise ImportError("Image download was incomplete. Please try again.")
            return bytes(content)
    except ImportError:
        raise
    except (OSError, ValueError, HTTPException, UnicodeError):
        raise ImportError("Could not download the image. Check the URL and try again.") from None
    finally:
        if connection is not None:
            connection.close()


def import_meme_url(metadata, url, *, data_dir=None):
    return import_meme(metadata, download_image(url), data_dir=data_dir)
