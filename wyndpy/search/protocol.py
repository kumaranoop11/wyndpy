"""SearcherProtocol — finds candidate URLs, never returns content itself.

A Searcher's output always re-enters the Fetcher chain (design spec §3,
Track B) rather than being treated as a source directly.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from wyndpy.core.results import Candidate


@runtime_checkable
class SearcherProtocol(Protocol):
    name: str  # adapter identifier used in config's `roles.search` list

    async def search(self, query: str, n: int = 10) -> list[Candidate]:
        """Return up to `n` candidate URLs ranked by relevance.

        A snippet is never treated as the source's content — only `url`
        is passed on to the Fetcher chain.
        """
        ...
