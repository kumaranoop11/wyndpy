"""ParserProtocol — converts a document/file (not a URL) into content."""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from wyndpy.core.results import RetrievalError, RetrievalResult


@runtime_checkable
class ParserProtocol(Protocol):
    name: str  # adapter identifier used in config's `roles.parse` list

    async def parse(self, data: bytes, mime_type: str) -> RetrievalResult | RetrievalError:
        """Convert file bytes into structured content.

        Implementations must compute content_hash via
        RetrievalResult.hash_body(data) — the same algorithm Fetcher
        adapters use, so hash-skip stays comparable across roles.
        """
        ...
