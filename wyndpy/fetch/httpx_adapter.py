"""Default Fetcher adapter: plain HTTP GET via httpx.

Cheapest tier in the escalation ladder — tried first, always. Enforces the
SSRF and size/timeout guards every Fetcher adapter is required to have
(design spec §9, Reliability). Reuses one httpx.AsyncClient across calls
for connection pooling rather than paying a fresh TCP/TLS handshake per
fetch — close() it (or use as an async context manager) when done.
"""
from __future__ import annotations

import concurrent.futures
import ipaddress
import logging
import re
import socket
from urllib.parse import urlparse

import httpx

from wyndpy.core.results import ErrorType, RetrievalError, RetrievalResult

logger = logging.getLogger("wyndpy.fetch.httpx")

DEFAULT_TIMEOUT_S = 15.0
DEFAULT_MAX_BYTES = 10 * 1024 * 1024  # 10 MB
EMPTY_SHELL_TEXT_THRESHOLD = 200  # visible chars after stripping tags/scripts
_DNS_TIMEOUT_S = 2.0


def _resolve_host(host: str) -> str:
    """Resolve with a hard timeout so a stuck DNS cannot pin the event loop."""
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    try:
        return pool.submit(socket.gethostbyname, host).result(timeout=_DNS_TIMEOUT_S)
    finally:
        pool.shutdown(wait=False, cancel_futures=True)


def _is_private_host(host: str) -> bool:
    try:
        ip = ipaddress.ip_address(host)
        return ip.is_private or ip.is_loopback or ip.is_link_local
    except ValueError:
        pass
    try:
        ip = ipaddress.ip_address(_resolve_host(host))
        return ip.is_private or ip.is_loopback or ip.is_link_local
    except (
        socket.gaierror,
        ValueError,
        OSError,
        concurrent.futures.TimeoutError,
    ):
        return False


class HttpxFetcher:
    """FetcherProtocol implementation backed by httpx.

    An empty ``allowlist_domains`` is fail-closed: every URL is rejected.
    Pass an explicit list, or let ``build_router()`` copy ``trust.allow``.
    """

    name = "httpx"
    implemented = True

    def __init__(
        self,
        allowlist_domains: list[str] | None = None,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        max_bytes: int = DEFAULT_MAX_BYTES,
        user_agent: str = "wyndpy-fetch/0.1",
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.allowlist_domains = allowlist_domains or []
        self.timeout_s = timeout_s
        self.max_bytes = max_bytes
        self.user_agent = user_agent
        # Reuse one client (connection pooling) unless the caller injects
        # its own — e.g. to share a pool across multiple adapter instances.
        self._client = client
        self._owns_client = client is None

    def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self.timeout_s,
                headers={"User-Agent": self.user_agent},
                follow_redirects=True,
            )
        return self._client

    async def close(self) -> None:
        """Release the underlying connection pool.

        Only closes a client this adapter created itself — an injected
        client is the caller's responsibility to close.
        """
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> HttpxFetcher:
        return self

    async def __aexit__(self, *exc_info) -> None:
        await self.close()

    def _url_allowed(self, url: str) -> bool:
        parsed = urlparse(url)
        if parsed.scheme != "https":
            return False
        if not parsed.hostname or _is_private_host(parsed.hostname):
            return False
        if not self.allowlist_domains:
            return False
        if not any(
            parsed.hostname == d or parsed.hostname.endswith(f".{d}")
            for d in self.allowlist_domains
        ):
            return False
        return True

    async def fetch(self, url: str) -> RetrievalResult | RetrievalError:
        """Fetch a URL over plain HTTPS and return its cleaned content."""
        if not self._url_allowed(url):
            logger.debug("rejected by allowlist/SSRF guard: %s", url)
            return RetrievalError(
                error_type=ErrorType.FORBIDDEN_URL,
                message=f"URL rejected by allowlist/SSRF guard: {url}",
                provider_used=self.name,
            )

        client = self._ensure_client()
        try:
            resp = await client.get(url)
        except httpx.TimeoutException:
            logger.debug("timeout fetching %s", url)
            return RetrievalError(
                error_type=ErrorType.TIMEOUT,
                message=f"Timed out fetching {url}",
                provider_used=self.name,
            )
        except httpx.HTTPError as exc:
            logger.debug("http error fetching %s: %s", url, exc)
            return RetrievalError(
                error_type=ErrorType.UNKNOWN,
                message=str(exc),
                provider_used=self.name,
            )

        # Redirect must not have left the allowlisted host
        if str(resp.url) != url and not self._url_allowed(str(resp.url)):
            logger.debug("redirect left allowlist: %s -> %s", url, resp.url)
            return RetrievalError(
                error_type=ErrorType.FORBIDDEN_URL,
                message=f"Redirect left allowlist: {resp.url}",
                provider_used=self.name,
            )

        if resp.status_code == 404:
            return RetrievalError(
                error_type=ErrorType.NOT_FOUND,
                message=f"404 for {url}",
                provider_used=self.name,
            )
        if resp.status_code == 429:
            return RetrievalError(
                error_type=ErrorType.RATE_LIMITED,
                message=f"429 for {url}",
                provider_used=self.name,
            )

        raw = resp.content[: self.max_bytes]
        content_type = resp.headers.get("content-type", "text/html")

        # Binary formats (PDF etc.) skip the HTML empty-shell heuristic
        # entirely — it's meaningless on non-text bodies and would
        # otherwise misfire as a false EMPTY_SHELL.
        if "pdf" in content_type or content_type.startswith("application/"):
            return RetrievalResult(
                content="",
                content_type=content_type,
                source_url=str(resp.url),
                content_hash=RetrievalResult.hash_body(raw),
                provider_used=self.name,
                raw_bytes=raw,
            )

        text = resp.text

        # crude empty-shell heuristic: strip tags, check visible length
        visible = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", text, flags=re.S)
        visible = re.sub(r"<[^>]+>", "", visible).strip()
        if len(visible) < EMPTY_SHELL_TEXT_THRESHOLD:
            logger.debug("empty-shell heuristic tripped for %s", url)
            return RetrievalError(
                error_type=ErrorType.EMPTY_SHELL,
                message="Visible text below threshold — likely JS-rendered",
                provider_used=self.name,
            )

        return RetrievalResult(
            content=text,
            content_type=content_type,
            source_url=str(resp.url),
            content_hash=RetrievalResult.hash_body(raw),
            provider_used=self.name,
            raw_bytes=raw,
        )
