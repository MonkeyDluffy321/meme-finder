"""Bounded HTTP downloads; validated redirects for images only."""

from http.client import HTTPConnection, HTTPSConnection, HTTPException
from ipaddress import IPv4Address, ip_address, ip_network
import socket
from time import monotonic
from urllib.parse import urljoin, urlsplit, urlunsplit

from utils.importer import ImportError, import_meme
from utils.uploads import MAX_BYTES


TIMEOUT = 5
MAX_IMAGE_REDIRECTS = 3
REDIRECT_STATUSES = {301, 302, 303, 307, 308}
NAT64_NETWORK = ip_network("64:ff9b::/96")


def _safe_public_ip(ip):
    if ip.version == 6 and ip in NAT64_NETWORK:
        # Only the well-known /96 translation prefix gets this exception.
        # Validate the actual IPv4 destination, not the translator's flags.
        ip = IPv4Address(int(ip) & 0xffffffff)
    return (ip.is_global and not any((ip.is_private, ip.is_loopback,
            ip.is_link_local, ip.is_multicast, ip.is_unspecified, ip.is_reserved)))


class _ImageRedirect(ImportError):
    pass


def download_resource(url, *, content_types=("image/",), max_bytes=MAX_BYTES, timeout=TIMEOUT,
                      respect_indexing=False, _image_redirects=False):
    """Shared safety layer for images and crawler HTML/robots responses."""
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
        ips = [ip_address(item[4][0]) for item in addresses]
        if not ips or any(not _safe_public_ip(ip) for ip in ips):
            raise ImportError("Image URLs must point to a public internet address.")
        # Pin the validated IP, while retaining the hostname for Host and TLS
        # certificate verification. A second DNS lookup cannot change the target.
        address = addresses[0][4][0]
        deadline = monotonic() + timeout
        connection_type = HTTPSConnection if parsed.scheme == "https" else HTTPConnection
        connection = connection_type(host, port, timeout=timeout)
        connection._create_connection = lambda *args, **kwargs: socket.create_connection(
            (address, port), timeout=max(0.001, deadline - monotonic()))
        connection.connect()
        transport = connection.sock
        transport.settimeout(max(0.001, deadline - monotonic()))
        connection.request("GET", (parsed.path or "/") + ("?" + parsed.query if parsed.query else ""),
                           headers={"User-Agent": "MemeFinder/1.0",
                                    "Accept": ", ".join(kind + "*" if kind.endswith("/") else kind
                                                        for kind in content_types),
                                    "Accept-Encoding": "identity"})
        with connection.getresponse() as response:
            if _image_redirects and response.status in REDIRECT_STATUSES:
                location = response.getheader("Location", "")
                if not location or any(ord(c) <= 32 or ord(c) == 127 for c in location) or "\\" in location:
                    raise ImportError("Image redirect has an invalid or missing Location.")
                if respect_indexing and any(token in response.getheader("X-Robots-Tag", "").lower()
                                            for token in ("noindex", "noimageindex", "none")):
                    raise ImportError("Source disallows indexing.")
                raise _ImageRedirect(location)
            if response.status != 200:
                if response.status in REDIRECT_STATUSES:
                    raise ImportError(f"HTTP {response.status} at {url}: this resource must be fetched without redirects.")
                raise ImportError(f"Download failed: HTTP {response.status} at {url}.")
            media_type = response.getheader("Content-Type", "").lower().split(";")[0].strip()
            if not any(media_type.startswith(kind) if kind.endswith("/") else media_type == kind
                       for kind in content_types):
                raise ImportError("The URL must return an image content type." if content_types == ("image/",)
                                  else "Unsupported response content type.")
            if respect_indexing and any(token in response.getheader("X-Robots-Tag", "").lower()
                                        for token in ("noindex", "noimageindex", "none")):
                raise ImportError("Source disallows indexing.")
            length = response.getheader("Content-Length")
            if length is not None and (int(length) < 0 or int(length) > max_bytes):
                raise ImportError("Choose an image up to 10 MB." if max_bytes == MAX_BYTES else "Response exceeds download limit.")
            content = bytearray()
            while len(content) <= max_bytes:
                remaining = deadline - monotonic()
                if remaining <= 0:
                    raise TimeoutError
                transport.settimeout(remaining)
                chunk = response.read1(min(64 * 1024, max_bytes + 1 - len(content)))
                if not chunk:
                    break
                content.extend(chunk)
            if len(content) > max_bytes:
                raise ImportError("Choose an image up to 10 MB." if max_bytes == MAX_BYTES else "Response exceeds download limit.")
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


def download_image(url, *, respect_indexing=False):
    seen = set()
    for hop in range(MAX_IMAGE_REDIRECTS + 1):
        try:
            parsed = urlsplit(url)
            identity = urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(),
                                   parsed.path or "/", parsed.query, ""))
        except (TypeError, ValueError):
            raise ImportError("Enter a valid HTTP or HTTPS image URL.") from None
        if identity in seen:
            raise ImportError("Image redirect loop detected.")
        seen.add(identity)
        try:
            # Each hop re-resolves, validates all addresses, and pins its socket
            # to the validated IP. Redirect responses are closed before following.
            return download_resource(url, respect_indexing=respect_indexing, _image_redirects=True)
        except _ImageRedirect as redirect:
            if hop == MAX_IMAGE_REDIRECTS:
                raise ImportError("Image redirect limit exceeded.") from None
            try:
                url = urljoin(url, str(redirect))
            except ValueError:
                raise ImportError("Image redirect has an invalid Location.") from None


def import_meme_url(metadata, url, *, data_dir=None):
    return import_meme(metadata, download_image(url), data_dir=data_dir)
