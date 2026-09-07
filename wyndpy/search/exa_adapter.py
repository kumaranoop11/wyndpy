"""Exa Searcher adapter — discovery-role adapter.

Only produces candidate URLs; never fetches content. ``search_fn`` is
injectable so tests never hit the network.
"""
from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from urllib.parse import urlparse

import httpx

from wyndpy.core.results import Candidate

logger = logging.getLogger("wyndpy.search.exa")

EXA_SEARCH_URL = "https://api.exa.ai/search"
DEFAULT_TIMEOUT_S = 20.0

SearchFn = Callable[[str, int], Awaitable[list[dict]]]


class SearchFailedError(RuntimeError):
    """Live Exa search failed. Not the same as an empty hit list."""


class ExaSearcher:
    """SearcherProtocol implementation backed by the Exa search API."""

    name = "exa"
    implemented = True

    def __init__(
        self,
        api_key: str,
        domain_allowlist: list[str] | None = None,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        search_fn: SearchFn | None = None,
    ) -> None:
        self.api_key = api_key
        self.domain_allowlist = domain_allowlist or []
        self.timeout_s = timeout_s
        self._search_fn = search_fn

    async def search(self, query: str, n: int = 10) -> list[Candidate]:
        if not self.api_key and self._search_fn is None:
            logger.debug("Exa API key is not set; returning no candidates")
            return []
        try:
            rows = await (
                self._search_fn(query, n)
                if self._search_fn
                else self._search_live(query, n)
            )
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            logger.warning("Exa search failed: %s", exc)
            raise SearchFailedError(str(exc)) from exc

        candidates: list[Candidate] = []
        for row in rows:
            url = str(row.get("url") or "")
            if not url or not self._host_allowed(url):
                continue
            score = row.get("score")
            try:
                relevance = float(score) if score is not None else 0.0
            except (TypeError, ValueError):
                relevance = 0.0
            snippet = str(row.get("title") or row.get("text") or "")[:240]
            candidates.append(
                Candidate(url=url, relevance_score=relevance, snippet=snippet)
            )
        return candidates

    def _host_allowed(self, url: str) -> bool:
        parsed = urlparse(url)
        if parsed.scheme != "https" or not parsed.hostname:
            return False
        if not self.domain_allowlist:
            return False
        host = parsed.hostname.lower()
        return any(host == d or host.endswith(f".{d}") for d in self.domain_allowlist)

    async def _search_live(self, query: str, n: int) -> list[dict]:
        payload: dict[str, object] = {"query": query, "numResults": n}
        if self.domain_allowlist:
            payload["includeDomains"] = self.domain_allowlist
        async with httpx.AsyncClient(timeout=self.timeout_s) as client:
            response = await client.post(
                EXA_SEARCH_URL,
                headers={
                    "x-api-key": self.api_key,
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            body = response.json()
        results = body.get("results") if isinstance(body, dict) else None
        if not isinstance(results, list):
            raise ValueError("Exa search response missing results")
        return [row for row in results if isinstance(row, dict)]
