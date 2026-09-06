"""TrustStrategy — decides whether a discovered source may leave pending_review."""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from wyndpy.core.results import Candidate


@runtime_checkable
class TrustStrategy(Protocol):
    async def is_trusted(self, candidate: Candidate) -> bool:
        """Return True only if this candidate may be treated as a source
        without requiring a human to approve it first.

        The default (AllowlistTrust) is conservative: nothing is trusted
        unless its domain matches an explicit allowlist entry, and even
        then `require_review` in policy can still force manual approval.
        """
        ...
