"""Shared result types every adapter normalizes into.

Core code never sees a tool-specific response shape — every Fetcher,
Searcher, and Parser adapter returns one of these.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum


class ErrorType(StrEnum):
    """Typed errors the router pattern-matches on to decide escalation."""

    EMPTY_SHELL = "empty_shell"           # JS-rendered page, no visible text
    UNSUPPORTED_FORMAT = "unsupported_format"
    NOT_FOUND = "not_found"
    TIMEOUT = "timeout"
    RATE_LIMITED = "rate_limited"
    FORBIDDEN_URL = "forbidden_url"        # SSRF / allowlist rejection
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class RetrievalResult:
    """Successful output of a Fetcher or Parser adapter."""

    content: str
    content_type: str
    source_url: str
    content_hash: str
    provider_used: str
    raw_bytes: bytes | None = None  # set by Fetcher adapters so a binary
                                     # body (e.g. a PDF) can be handed to a
                                     # Parser adapter without re-fetching
    retrieved_at: datetime = field(
        default_factory=lambda: datetime.now(UTC)
    )

    @staticmethod
    def hash_body(raw: bytes) -> str:
        """SHA-256 of the raw response body.

        Pinned to one algorithm so hash-skip works identically across
        every adapter and every re-fetch (see design spec §2).
        """
        return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class RetrievalError:
    """Failed output of a Fetcher or Parser adapter."""

    error_type: ErrorType
    message: str
    provider_used: str


@dataclass(frozen=True)
class Candidate:
    """One result from a Searcher adapter — a candidate URL, not content."""

    url: str
    relevance_score: float
    snippet: str
