import ipaddress
import socket
from urllib.parse import urljoin, urlparse

import httpx

MAX_RESPONSE_BYTES = 2 * 1024 * 1024  # 2MB
FETCH_TIMEOUT_SECONDS = 10.0


class FetcherError(Exception):
    """Base exception for fetcher errors."""

    pass


class SSRFBlockedError(FetcherError):
    """Raised when a URL resolves to a forbidden/private IP range."""

    pass


class PayloadTooLargeError(FetcherError):
    """Raised when the response body exceeds 2MB."""

    pass


class FetchTimeoutError(FetcherError):
    """Raised when fetching the URL times out."""

    pass


# Aliases for backwards compatibility
FetcherException = FetcherError
SSRFBlockedException = SSRFBlockedError
PayloadTooLargeException = PayloadTooLargeError
FetchTimeoutException = FetchTimeoutError


def is_ip_blocked(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
        return (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        )
    except ValueError:
        return True


def validate_url_and_resolve(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("Only http and https schemes are supported")

    hostname = parsed.hostname
    if not hostname:
        raise ValueError("Invalid URL: missing hostname")

    if hostname.lower() in ("localhost", "localhost.localdomain"):
        raise SSRFBlockedError(f"Forbidden host: {hostname}")

    try:
        addr_info = socket.getaddrinfo(hostname, None)
        for entry in addr_info:
            ip_str = entry[4][0]
            if is_ip_blocked(ip_str):
                raise SSRFBlockedError(f"Resolved to forbidden IP: {ip_str}")
    except socket.gaierror as e:
        msg = f"DNS resolution failed for host {hostname}: {e}"
        raise SSRFBlockedError(msg) from e


async def fetch_article_url(url: str) -> str:
    """Fetch article HTML from a URL with SSRF guard, 10s timeout, and 2MB cap."""
    validate_url_and_resolve(url)

    current_url = url
    max_redirects = 5

    user_agent = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36 (CoverageAmplifier/1.0)"
    )

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(FETCH_TIMEOUT_SECONDS),
        follow_redirects=False,
    ) as client:
        for _ in range(max_redirects + 1):
            validate_url_and_resolve(current_url)

            try:
                request = client.build_request(
                    "GET",
                    current_url,
                    headers={
                        "User-Agent": user_agent,
                        "Accept": (
                            "text/html,application/xhtml+xml,application/xml;"
                            "q=0.9,*/*;q=0.8"
                        ),
                    },
                )
                response = await client.send(request, stream=True)
            except httpx.TimeoutException as e:
                raise FetchTimeoutError(f"Fetch timed out for {current_url}") from e
            except httpx.RequestError as e:
                raise FetcherError(f"Network error fetching {current_url}: {e}") from e

            # Handle redirects manually to protect against redirect-based SSRF
            if response.status_code in (301, 302, 303, 307, 308):
                location = response.headers.get("Location")
                if not location:
                    break
                await response.aclose()
                current_url = urljoin(current_url, location)
                continue

            response.raise_for_status()

            # Check Content-Length header if present
            content_length = response.headers.get("Content-Length")
            if content_length:
                try:
                    if int(content_length) > MAX_RESPONSE_BYTES:
                        await response.aclose()
                        raise PayloadTooLargeError(
                            f"Content-Length {content_length} exceeds 2MB limit"
                        )
                except ValueError:
                    pass

            # Stream body up to 2MB cap
            chunks: list[bytes] = []
            total_bytes = 0
            try:
                async for chunk in response.aiter_bytes():
                    total_bytes += len(chunk)
                    if total_bytes > MAX_RESPONSE_BYTES:
                        raise PayloadTooLargeError(
                            f"Downloaded bytes exceeded 2MB limit: {total_bytes}"
                        )
                    chunks.append(chunk)
            finally:
                await response.aclose()

            content_bytes = b"".join(chunks)
            encoding = response.encoding or "utf-8"
            return content_bytes.decode(encoding, errors="replace")

    raise FetcherError(f"Too many redirects fetching {url}")
