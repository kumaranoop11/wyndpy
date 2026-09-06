"""FetcherProtocol — the only shape a fetch-role adapter must satisfy.

Any adapter implementing this (httpx, Firecrawl, or a future replacement)
is interchangeable to the router. Core code never imports a concrete
adapter class, only this protocol.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from wyndpy.core.results import RetrievalError, RetrievalResult


@runtime_checkable
class FetcherProtocol(Protocol):
    name: str  # adapter identifier used in config's `roles.fetch` list

    async def fetch(self, url: str) -> RetrievalResult | RetrievalError:
        """Retrieve content from a known URL.

        Implementations must:
        - enforce SSRF protections (no IP literals, file://, localhost,
          private ranges; redirects only followed within the same
          allowlisted host)
        - enforce a timeout and max response size
        - compute content_hash via RetrievalResult.hash_body(raw_bytes)
        - return a typed RetrievalError (never raise) on failure
        """
        ...
