"""Firecrawl Fetcher adapter — escalation tier for JS-rendered pages.

Only invoked by the router when the default httpx adapter returns
EMPTY_SHELL. Fill in the actual Firecrawl API call before use; the
surrounding shape (allowlist check, hashing, typed errors) mirrors
HttpxFetcher so both satisfy the same FetcherProtocol identically.
"""
from __future__ import annotations

from wyndpy.core.results import RetrievalError, RetrievalResult


class FirecrawlFetcher:
    """FetcherProtocol implementation backed by the Firecrawl API."""

    name = "firecrawl"
    implemented = False

    def __init__(
        self,
        api_key: str,
        allowlist_domains: list[str] | None = None,
        timeout_s: float = 30.0,
    ) -> None:
        self.api_key = api_key
        self.allowlist_domains = allowlist_domains or []
        self.timeout_s = timeout_s

    async def fetch(self, url: str) -> RetrievalResult | RetrievalError:
        # TODO: call Firecrawl's scrape endpoint, requesting markdown output.
        # On success, wrap into RetrievalResult with:
        #   content_hash = RetrievalResult.hash_body(raw_response_bytes)
        #   provider_used = self.name
        # On failure, map Firecrawl's error into one of the ErrorType values
        # (e.g. still-empty result -> ErrorType.EMPTY_SHELL, so an even
        # higher tier — if one is ever configured — can take over).
        raise NotImplementedError(
            "Wire up the Firecrawl API call here; adapter shape and "
            "allowlist/SSRF checks should mirror HttpxFetcher."
        )
