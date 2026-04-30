from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.services.url_content_fetch_service import fetch_url_text_excerpt, validate_public_http_url


class _MockResponse:
    def __init__(self, *, content: bytes, content_type: str = "text/html; charset=utf-8", status_code: int = 200):
        self.content = content
        self.status_code = status_code
        self.headers = {"content-type": content_type}

    def raise_for_status(self) -> None:
        return None


async def test_fetch_url_text_excerpt_extracts_visible_html_text():
    html = b"""
    <html><head><style>.x{}</style><script>ignore()</script></head>
    <body><h1>Random Forest</h1><p>Ensemble learning with decision trees.</p></body></html>
    """
    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = False
    mock_client.get = AsyncMock(return_value=_MockResponse(content=html))

    with (
        patch("app.services.url_content_fetch_service.socket.getaddrinfo", return_value=[(None, None, None, None, ("93.184.216.34", 443))]),
        patch("httpx.AsyncClient", return_value=mock_client),
    ):
        result = await fetch_url_text_excerpt("https://example.com/random-forest")

    assert result.quality_status == "url_body_fetched"
    assert "Random Forest" in result.raw_text_excerpt
    assert "Ensemble learning" in result.raw_text_excerpt
    assert "ignore" not in result.raw_text_excerpt
    assert result.metadata["url_fetch"]["status"] == "fetched"


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "http://localhost/admin",
        "http://127.0.0.1/admin",
        "http://169.254.169.254/latest/meta-data",
        "https://metadata.google.internal/computeMetadata/v1",
    ],
)
def test_validate_public_http_url_blocks_non_public_targets(url):
    with pytest.raises(ValueError):
        validate_public_http_url(url)


async def test_fetch_url_text_excerpt_reports_unsupported_content_type():
    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = False
    mock_client.get = AsyncMock(return_value=_MockResponse(content=b"%PDF", content_type="application/pdf"))

    with (
        patch("app.services.url_content_fetch_service.socket.getaddrinfo", return_value=[(None, None, None, None, ("93.184.216.34", 443))]),
        patch("httpx.AsyncClient", return_value=mock_client),
    ):
        result = await fetch_url_text_excerpt("https://example.com/paper.pdf")

    assert result.raw_text_excerpt is None
    assert result.quality_status == "url_body_unavailable"
    assert result.metadata["url_fetch"]["status"] == "unsupported_content_type"
