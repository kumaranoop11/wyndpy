"""Default TrustStrategy: domain allowlist, config-driven."""
from __future__ import annotations

from urllib.parse import urlparse

from wyndpy.core.results import Candidate


class AllowlistTrust:
    """Trusts a candidate only if its host matches an allowlist entry."""

    def __init__(self, allow: list[str] | None = None) -> None:
        self.allow = allow or []

    async def is_trusted(self, candidate: Candidate) -> bool:
        host = urlparse(candidate.url).hostname or ""
        for pattern in self.allow:
            pattern = pattern.lstrip("*.")
            if host == pattern or host.endswith(f".{pattern}"):
                return True
        return False
