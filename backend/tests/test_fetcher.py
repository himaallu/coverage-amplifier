from unittest.mock import AsyncMock, patch

import httpx
import pytest

from backend.app.extraction.fetcher import (
    FetchTimeoutException,
    PayloadTooLargeException,
    SSRFBlockedException,
    fetch_article_url,
)

PUBLIC_IP_ADDRINFO = [(None, None, None, None, ("93.184.216.34", 443))]


@pytest.mark.anyio
async def test_fetcher_blocks_non_http_schemes() -> None:
    with pytest.raises(ValueError, match="Only http and https schemes are supported"):
        await fetch_article_url("ftp://example.com/article")

    with pytest.raises(ValueError, match="Only http and https schemes are supported"):
        await fetch_article_url("file:///etc/passwd")


@pytest.mark.anyio
@pytest.mark.parametrize(
    "blocked_url",
    [
        "http://127.0.0.1/article",
        "http://localhost/article",
        "http://10.0.0.5/news",
        "http://192.168.1.100/page",
        "http://172.16.0.2/article",
        "http://169.254.169.254/latest/meta-data/",
    ],
)
async def test_fetcher_blocks_private_ip_ssrf(blocked_url: str) -> None:
    with pytest.raises(SSRFBlockedException):
        await fetch_article_url(blocked_url)


@pytest.mark.anyio
async def test_fetcher_blocks_redirect_to_private_ip() -> None:
    mock_redirect_response = httpx.Response(
        status_code=302,
        headers={"Location": "http://127.0.0.1:8000/secret"},
        request=httpx.Request("GET", "https://public.example.com/link"),
    )

    with patch("httpx.AsyncClient.send", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = mock_redirect_response
        with pytest.raises(SSRFBlockedException):
            await fetch_article_url("https://public.example.com/link")


@pytest.mark.anyio
async def test_fetcher_enforces_2mb_limit() -> None:
    huge_data = b"a" * (2 * 1024 * 1024 + 10)
    mock_response = httpx.Response(
        status_code=200,
        content=huge_data,
        request=httpx.Request("GET", "https://public.example.com/huge"),
    )

    with (
        patch("socket.getaddrinfo", return_value=PUBLIC_IP_ADDRINFO),
        patch("httpx.AsyncClient.send", new_callable=AsyncMock) as mock_send,
    ):
        mock_send.return_value = mock_response
        with pytest.raises(PayloadTooLargeException):
            await fetch_article_url("https://public.example.com/huge")


@pytest.mark.anyio
async def test_fetcher_enforces_10s_timeout() -> None:
    with (
        patch("socket.getaddrinfo", return_value=PUBLIC_IP_ADDRINFO),
        patch("httpx.AsyncClient.send", new_callable=AsyncMock) as mock_send,
    ):
        mock_send.side_effect = httpx.TimeoutException("Connection timed out")
        with pytest.raises(FetchTimeoutException):
            await fetch_article_url("https://public.example.com/slow")


@pytest.mark.anyio
async def test_fetcher_happy_path() -> None:
    html_content = (
        "<html><body><h1>Sample News</h1>" "<p>Article body here.</p></body></html>"
    )
    mock_response = httpx.Response(
        status_code=200,
        text=html_content,
        headers={"Content-Type": "text/html"},
        request=httpx.Request("GET", "https://public.example.com/article"),
    )

    with (
        patch("socket.getaddrinfo", return_value=PUBLIC_IP_ADDRINFO),
        patch("httpx.AsyncClient.send", new_callable=AsyncMock) as mock_send,
    ):
        mock_send.return_value = mock_response
        result = await fetch_article_url("https://public.example.com/article")
        assert "Article body here." in result


@pytest.mark.anyio
async def test_fetcher_missing_hostname() -> None:
    with pytest.raises(ValueError, match="missing hostname"):
        await fetch_article_url("http:///empty-host")


@pytest.mark.anyio
async def test_fetcher_network_request_error() -> None:
    with (
        patch("socket.getaddrinfo", return_value=PUBLIC_IP_ADDRINFO),
        patch("httpx.AsyncClient.send", new_callable=AsyncMock) as mock_send,
    ):
        mock_send.side_effect = httpx.ConnectError("Connection refused")
        with pytest.raises(Exception):
            await fetch_article_url("https://public.example.com/error")


@pytest.mark.anyio
async def test_fetcher_content_length_header_too_large() -> None:
    mock_response = httpx.Response(
        status_code=200,
        headers={"Content-Length": "3000000"},
        request=httpx.Request("GET", "https://public.example.com/big"),
    )
    with (
        patch("socket.getaddrinfo", return_value=PUBLIC_IP_ADDRINFO),
        patch("httpx.AsyncClient.send", new_callable=AsyncMock) as mock_send,
    ):
        mock_send.return_value = mock_response
        with pytest.raises(PayloadTooLargeException):
            await fetch_article_url("https://public.example.com/big")


@pytest.mark.anyio
async def test_fetcher_too_many_redirects() -> None:
    redirect_resp = httpx.Response(
        status_code=301,
        headers={"Location": "https://public.example.com/loop"},
        request=httpx.Request("GET", "https://public.example.com/loop"),
    )
    with (
        patch("socket.getaddrinfo", return_value=PUBLIC_IP_ADDRINFO),
        patch("httpx.AsyncClient.send", new_callable=AsyncMock) as mock_send,
    ):
        mock_send.return_value = redirect_resp
        with pytest.raises(Exception, match="Too many redirects"):
            await fetch_article_url("https://public.example.com/loop")
