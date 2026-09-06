"""ResolvableItem — the one domain-blind shape core code operates on.

A project's "SKU", "legal clause", "product review", etc. all become a
ResolvableItem before touching any Wyndpy internals. `metadata` is opaque
to core; only a project's own TrustStrategy / ItemQueryBuilder look inside it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class ItemStatus(StrEnum):
    RESOLVED = "resolved"
    UNRESOLVED = "unresolved"            # Searcher found nothing usable
    FETCH_EXHAUSTED = "fetch_exhausted"  # source known, every adapter failed
    PENDING_DISCOVERY = "pending_discovery"
    PENDING_REVIEW = "pending_review"    # a new source was discovered, not
                                          # yet approved (merge rule: no
                                          # prior registry entry)


@dataclass
class ResolvableItem:
    id: str
    query_hint: str
    current_sources: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    status: ItemStatus = ItemStatus.PENDING_DISCOVERY
    last_content_hash: str | None = None
    candidate_sources: list[str] = field(default_factory=list)
    # alternate sources found while current_sources was already non-empty —
    # staged for review, never auto-promoted into current_sources (merge
    # rule: existing registry entry)
    discovered_urls_seen: set[str] = field(default_factory=set)
    # every URL ever surfaced by discovery for this item, so a repeat
    # discovery hit can be silently discarded (merge rule: duplicate)
