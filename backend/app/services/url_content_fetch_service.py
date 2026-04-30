from __future__ import annotations

import ipaddress
import json
import re
import socket
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpx

MAX_URL_FETCH_BYTES = 200_000
MAX_URL_TEXT_CHARS = 8_000
MAX_REDIRECTS = 3
URL_FETCH_TIMEOUT_SECONDS = 8.0
ALLOWED_CONTENT_TYPES = ("text/html", "text/plain", "application/xhtml+xml")
METADATA_IPS = {
    ipaddress.ip_address("100.100.100.200"),
    ipaddress.ip_address("169.254.169.254"),
    ipaddress.ip_address("169.254.170.2"),
}


@dataclass(frozen=True)
class UrlContentFetchResult:
    raw_text_excerpt: str | None
    summary: str | None
    quality_status: str
    metadata: dict[str, Any]


class _VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._hidden_depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in {"script", "style", "noscript", "svg"}:
            self._hidden_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style", "noscript", "svg"} and self._hidden_depth > 0:
            self._hidden_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._hidden_depth == 0:
            text = data.strip()
            if text:
                self.parts.append(text)


class UrlFetchBlocked(ValueError):
    pass


def _is_blocked_ip(value: str) -> bool:
    try:
        target_ip = ipaddress.ip_address(value)
    except ValueError:
        return True
    return (
        target_ip in METADATA_IPS
        or target_ip.is_private
        or target_ip.is_loopback
        or target_ip.is_link_local
        or target_ip.is_multicast
        or target_ip.is_reserved
        or target_ip.is_unspecified
    )


def validate_public_http_url(url: str) -> str:
    normalized = url.strip()
    try:
        parts = urlsplit(normalized)
        port = parts.port
    except ValueError as exc:
        raise UrlFetchBlocked("invalid_url") from exc

    if parts.scheme not in {"http", "https"} or not parts.hostname:
        raise UrlFetchBlocked("unsupported_url_scheme")
    if parts.username or parts.password:
        raise UrlFetchBlocked("url_credentials_not_allowed")

    hostname = parts.hostname.strip().lower()
    if hostname == "localhost" or hostname.endswith(".local") or hostname == "metadata.google.internal":
        raise UrlFetchBlocked("private_or_metadata_host")

    try:
        direct_ip = ipaddress.ip_address(hostname)
    except ValueError:
        try:
            resolved_ips = {
                item[4][0]
                for item in socket.getaddrinfo(hostname, port or None, proto=socket.IPPROTO_TCP)
            }
        except socket.gaierror as exc:
            raise UrlFetchBlocked("dns_resolution_failed") from exc
        if not resolved_ips or any(_is_blocked_ip(ip) for ip in resolved_ips):
            raise UrlFetchBlocked("private_or_metadata_host")
    else:
        if _is_blocked_ip(str(direct_ip)):
            raise UrlFetchBlocked("private_or_metadata_host")

    return normalized


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _extract_text(content: bytes, content_type: str) -> str:
    encoding = "utf-8"
    match = re.search(r"charset=([^;]+)", content_type, flags=re.IGNORECASE)
    if match:
        encoding = match.group(1).strip()
    decoded = content.decode(encoding, errors="ignore")
    if "html" not in content_type.lower():
        return _normalize_text(decoded)
    parser = _VisibleTextParser()
    parser.feed(decoded)
    return _normalize_text(" ".join(parser.parts))


def _metadata(status: str, **fields: Any) -> dict[str, Any]:
    return {
        "url_fetch": {
            "status": status,
            "max_bytes": MAX_URL_FETCH_BYTES,
            "max_text_chars": MAX_URL_TEXT_CHARS,
            **fields,
        }
    }


def _result(raw_text_excerpt: str | None, *, status: str, **metadata_fields: Any) -> UrlContentFetchResult:
    summary = raw_text_excerpt[:300] if raw_text_excerpt else None
    return UrlContentFetchResult(
        raw_text_excerpt=raw_text_excerpt,
        summary=summary,
        quality_status="url_body_fetched" if raw_text_excerpt else "url_body_unavailable",
        metadata=_metadata(status, **metadata_fields),
    )


async def fetch_url_text_excerpt(url: str) -> UrlContentFetchResult:
    try:
        current_url = validate_public_http_url(url)
    except UrlFetchBlocked as exc:
        return _result(None, status=str(exc))

    headers = {
        "User-Agent": "LearnPath-KG URL Fetcher/0.1",
        "Accept": "text/html,text/plain;q=0.9,*/*;q=0.1",
    }
    try:
        async with httpx.AsyncClient(timeout=URL_FETCH_TIMEOUT_SECONDS, follow_redirects=False) as client:
            for redirect_index in range(MAX_REDIRECTS + 1):
                response = await client.get(current_url, headers=headers)
                if response.status_code in {301, 302, 303, 307, 308}:
                    location = response.headers.get("location")
                    if not location or redirect_index >= MAX_REDIRECTS:
                        return _result(None, status="redirect_limit_exceeded", http_status=response.status_code)
                    try:
                        current_url = validate_public_http_url(urljoin(current_url, location))
                    except UrlFetchBlocked as exc:
                        return _result(None, status=f"redirect_{exc}", http_status=response.status_code)
                    continue
                response.raise_for_status()
                content_type = response.headers.get("content-type", "").lower()
                if not any(content_type.startswith(allowed) for allowed in ALLOWED_CONTENT_TYPES):
                    return _result(None, status="unsupported_content_type", content_type=content_type)
                content = response.content
                truncated = len(content) > MAX_URL_FETCH_BYTES
                if truncated:
                    content = content[:MAX_URL_FETCH_BYTES]
                text = _extract_text(content, content_type)[:MAX_URL_TEXT_CHARS]
                if not text:
                    return _result(None, status="empty_body", content_type=content_type)
                return _result(
                    text,
                    status="fetched",
                    final_url=current_url,
                    http_status=response.status_code,
                    content_type=content_type,
                    truncated=truncated,
                )
    except (httpx.HTTPError, UnicodeError) as exc:
        return _result(None, status="fetch_failed", error=exc.__class__.__name__)

    return _result(None, status="fetch_failed")


def merge_url_fetch_metadata(metadata_json: str | None, fetch_metadata: dict[str, Any]) -> str:
    try:
        metadata = json.loads(metadata_json) if metadata_json else {}
    except json.JSONDecodeError:
        metadata = {"raw_metadata": metadata_json}
    if not isinstance(metadata, dict):
        metadata = {"raw_metadata": metadata}
    metadata.update(fetch_metadata)
    return json.dumps(metadata, ensure_ascii=False, sort_keys=True)
