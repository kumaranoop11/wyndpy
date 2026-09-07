"""Firecrawl Fetcher adapter — escalation tier for JS-rendered pages.

Called by the router when httpx returns EMPTY_SHELL. Uses the Firecrawl
scrape REST API. ``scrape`` is injectable so tests never hit the network.
"""
from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from urllib.parse import urlparse

import httpx

from wyndpy.core.results import ErrorType, RetrievalError, RetrievalResult
from wyndpy.fetch.httpx_adapter import _is_private_host

logger = logging.getLogger("wyndpy.fetch.firecrawl")

FIRECRAWL_SCRAPE_URL = "https://api.firecrawl.dev/v1/scrape"
DEFAULT_TIMEOUT_S = 30.0
DEFAULT_MAX_BYTES = 10 * 1024 * 1024

ScrapeFn = Callable[[str], Awaitable[dict]]


class FirecrawlFetcher:
    """FetcherProtocol implementation backed by the Firecrawl scrape API."""

    name = "firecrawl"
    implemented = True

    def __init__(
        self,
        api_key: str,
        allowlist_domains: list[str] | None = None,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        max_bytes: int = DEFAULT_MAX_BYTES,
        scrape: ScrapeFn | None = None,
    ) -> None:
        self.api_key = api_key
        self.allowlist_domains = allowlist_domains or []
        self.timeout_s = timeout_s
        self.max_bytes = max_bytes
        self._scrape = scrape

    def _url_allowed(self, url: str) -> bool:
        parsed = urlparse(url)
        if parsed.scheme != "https" or not parsed.hostname:
            return False
        if _is_private_host(parsed.hostname):
            return False
        if not self.allowlist_domains:
            return False
        host = parsed.hostname.lower()
        return any(host == d or host.endswith(f".{d}") for d in self.allowlist_domains)

    async def fetch(self, url: str) -> RetrievalResult | RetrievalError:
        if not self._url_allowed(url):
            return RetrievalError(
                error_type=ErrorType.FORBIDDEN_URL,
                message=f"URL rejected by allowlist/SSRF guard: {url}",
                provider_used=self.name,
            )
        if not self.api_key and self._scrape is None:
            return RetrievalError(
                error_type=ErrorType.UNKNOWN,
                message="Firecrawl API key is not set",
                provider_used=self.name,
            )
        try:
            payload = await (self._scrape(url) if self._scrape else self._scrape_live(url))
        except httpx.TimeoutException:
            return RetrievalError(
                error_type=ErrorType.TIMEOUT,
                message=f"Timed out scraping {url}",
                provider_used=self.name,
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 429:
                return RetrievalError(
                    error_type=ErrorType.RATE_LIMITED,
                    message=f"429 from Firecrawl for {url}",
                    provider_used=self.name,
                )
            return RetrievalError(
                error_type=ErrorType.UNKNOWN,
                message=str(exc),
                provider_used=self.name,
            )
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            return RetrievalError(
                error_type=ErrorType.UNKNOWN,
                message=str(exc),
                provider_used=self.name,
            )

        markdown = str(payload.get("markdown") or "")
        html = str(payload.get("html") or "")
        text = markdown or html
        raw = text.encode("utf-8")
        if len(raw) > self.max_bytes:
            return RetrievalError(
                error_type=ErrorType.UNKNOWN,
                message=f"Firecrawl body exceeded {self.max_bytes} bytes",
                provider_used=self.name,
            )
        if not text.strip():
            return RetrievalError(
                error_type=ErrorType.EMPTY_SHELL,
                message="Firecrawl returned no visible content",
                provider_used=self.name,
            )
        return RetrievalResult(
            content=text,
            content_type="text/markdown" if markdown else "text/html",
            source_url=url,
            content_hash=RetrievalResult.hash_body(raw),
            provider_used=self.name,
            raw_bytes=raw,
        )

    async def _scrape_live(self, url: str) -> dict:
        async with httpx.AsyncClient(timeout=self.timeout_s) as client:
            response = await client.post(
                FIRECRAWL_SCRAPE_URL,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={"url": url, "formats": ["markdown", "html"]},
            )
            response.raise_for_status()
            body = response.json()
        data = body.get("data") if isinstance(body, dict) else None
        if not isinstance(data, dict):
            raise ValueError("Firecrawl scrape response missing data")
        return data
