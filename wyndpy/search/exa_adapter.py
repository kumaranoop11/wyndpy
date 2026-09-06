"""Exa Searcher adapter — default discovery-role adapter.

Only produces candidate URLs; never fetches content itself. A discovered
URL always re-enters the Fetcher chain via the router.
"""
from __future__ import annotations

from wyndpy.core.results import Candidate


class ExaSearcher:
    """SearcherProtocol implementation backed by the Exa API."""

    name = "exa"
    implemented = False

    def __init__(self, api_key: str, domain_allowlist: list[str] | None = None) -> None:
        self.api_key = api_key
        self.domain_allowlist = domain_allowlist or []

    async def search(self, query: str, n: int = 10) -> list[Candidate]:
        # TODO: call Exa's /search endpoint with `query`, num_results=n,
        # and include_domains=self.domain_allowlist if set. Map each hit to:
        #   Candidate(url=..., relevance_score=..., snippet=...)
        # Never surface the snippet downstream as content — it's for the
        # trust/review layer only, not a substitute for fetching the URL.
        raise NotImplementedError(
            "Wire up the Exa API call here; return list[Candidate]."
        )
