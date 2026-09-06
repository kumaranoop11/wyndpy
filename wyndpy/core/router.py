"""Router — the only place escalation logic lives.

Core code (this file) never imports a concrete adapter class, only the
protocols. Two modes of escalation are supported:

- **Legacy/standalone** (no `escalation_rules` passed in): walks
  `self.fetchers` in list order, escalating on any error in
  `ESCALATABLE_ERRORS`. This is what a project gets for free when using
  adapters directly, with no policy file (design spec §1, principle 3 —
  "everything usable standalone").
- **Config-driven** (`escalation_rules` passed in, normally built from a
  project's policy.yaml via `wyndpy.factory.build_router`): walks a graph
  keyed by (from_adapter, trigger) -> to_adapter, so config actually
  decides behavior, not a hardcoded set in this file.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from wyndpy.core.escalation import EscalationRule, content_type_trigger
from wyndpy.core.item import ItemStatus, ResolvableItem
from wyndpy.core.results import (
    Candidate,
    ErrorType,
    RetrievalError,
    RetrievalResult,
)
from wyndpy.fetch.protocol import FetcherProtocol
from wyndpy.parse.protocol import ParserProtocol
from wyndpy.registry.protocol import RegistryProtocol
from wyndpy.search.protocol import SearcherProtocol
from wyndpy.trust.protocol import TrustStrategy

logger = logging.getLogger("wyndpy.router")

# Legacy/standalone default: errors that mean "try the next adapter in the
# list" when no explicit escalation_rules are configured.
ESCALATABLE_ERRORS = {ErrorType.EMPTY_SHELL, ErrorType.TIMEOUT}

# Errors worth retrying on the *same* adapter before giving up on it —
# distinct from escalation, which moves to a *different* adapter.
RETRYABLE_ERRORS = {ErrorType.TIMEOUT, ErrorType.RATE_LIMITED}


@dataclass
class RouterConfig:
    candidate_count: int = 10
    require_review: bool = True
    retry_attempts: int = 0          # per-adapter retries before escalating
    retry_backoff_base_s: float = 0.2


class Router:
    """Walks Track A (fetch) and drives Track B (discovery).

    One in-flight lock per item_id gives single-flight behavior: two
    concurrent callers resolving the same item coalesce into one attempt
    (design spec §9, Concurrency).
    """

    def __init__(
        self,
        fetchers: list[FetcherProtocol],
        searchers: list[SearcherProtocol],
        parsers: list[ParserProtocol],
        trust: TrustStrategy,
        registry: RegistryProtocol,
        config: RouterConfig | None = None,
        escalation_rules: list[EscalationRule] | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.fetchers = fetchers
        self.searchers = searchers
        self.parsers = parsers
        self.trust = trust
        self.registry = registry
        self.config = config or RouterConfig()
        self.escalation_rules = escalation_rules or []
        self._sleep = sleep

        self._fetcher_by_name = {f.name: f for f in fetchers}
        self._parser_by_name = {p.name: p for p in parsers}
        self._locks: dict[str, asyncio.Lock] = {}

        # (from_adapter, error_type_value) -> to_adapter_name
        self._error_escalations: dict[tuple[str, str], str] = {}
        # (from_adapter, mime_type) -> parser_adapter_name
        self._content_type_escalations: dict[tuple[str, str], str] = {}
        for rule in self.escalation_rules:
            mime = content_type_trigger(rule)
            key_from = rule.from_ or "*"
            if mime:
                self._content_type_escalations[(key_from, mime)] = rule.to
            else:
                self._error_escalations[(key_from, rule.trigger)] = rule.to

    def _lock_for(self, item_id: str) -> asyncio.Lock:
        return self._locks.setdefault(item_id, asyncio.Lock())

    def _next_fetcher_config_driven(
        self, current_name: str, error_type: ErrorType
    ) -> FetcherProtocol | None:
        to_name = self._error_escalations.get(
            (current_name, error_type.value)
        ) or self._error_escalations.get(("*", error_type.value))
        if to_name is None:
            return None
        return self._fetcher_by_name.get(to_name)

    def _parser_for_content_type(
        self, current_name: str, content_type: str
    ) -> ParserProtocol | None:
        # exact match first, then wildcard-from, then a bare "pdf" fallback
        to_name = self._content_type_escalations.get(
            (current_name, content_type)
        ) or self._content_type_escalations.get(("*", content_type))
        if to_name:
            return self._parser_by_name.get(to_name)
        if "pdf" in content_type and self.parsers:
            return self.parsers[0]
        return None

    # ---- Track A: fast path ------------------------------------------------

    async def resolve_known_source(
        self, item: ResolvableItem
    ) -> RetrievalResult | RetrievalError:
        """Fetch `item`'s known source(s), escalating on failure per the
        rules above. Returns the final result/error and updates
        item.status accordingly.
        """
        async with self._lock_for(item.id):
            if not item.current_sources:
                raise ValueError(f"{item.id} has no known source for Track A")
            if not self.fetchers:
                return RetrievalError(
                    error_type=ErrorType.UNKNOWN,
                    message="No fetchers configured",
                    provider_used="none",
                )

            url = item.current_sources[0]
            current: FetcherProtocol | None = self.fetchers[0]
            legacy_mode = not self.escalation_rules
            legacy_idx = 0
            last_error: RetrievalError | None = None
            visited: set[int] = set()

            while current is not None and id(current) not in visited:
                visited.add(id(current))
                logger.debug("item=%s: attempting fetcher=%s", item.id, current.name)
                outcome = await self._fetch_with_retry(current, url)

                if isinstance(outcome, RetrievalResult):
                    if outcome.content_hash == item.last_content_hash:
                        logger.debug(
                            "item=%s: hash-skip via fetcher=%s (unchanged)",
                            item.id, current.name,
                        )
                        item.status = ItemStatus.RESOLVED
                        await self.registry.upsert(item)
                        return outcome

                    parser = self._parser_for_content_type(
                        current.name, outcome.content_type
                    )
                    if parser is not None:
                        logger.debug(
                            "item=%s: fetcher=%s content_type=%s -> parser=%s",
                            item.id, current.name, outcome.content_type, parser.name,
                        )
                        return await self._run_parser(parser, outcome)

                    logger.info(
                        "item=%s: resolved via fetcher=%s", item.id, current.name
                    )
                    item.last_content_hash = outcome.content_hash
                    item.status = ItemStatus.RESOLVED
                    await self.registry.upsert(item)
                    return outcome

                last_error = outcome
                logger.debug(
                    "item=%s: fetcher=%s failed error_type=%s",
                    item.id, current.name, outcome.error_type.value,
                )

                if legacy_mode:
                    legacy_idx += 1
                    if (
                        outcome.error_type not in ESCALATABLE_ERRORS
                        or legacy_idx >= len(self.fetchers)
                    ):
                        current = None
                    else:
                        current = self.fetchers[legacy_idx]
                        logger.debug(
                            "item=%s: escalating (legacy order) to fetcher=%s",
                            item.id, current.name,
                        )
                else:
                    next_fetcher = self._next_fetcher_config_driven(
                        current.name, outcome.error_type
                    )
                    if next_fetcher is not None:
                        logger.debug(
                            "item=%s: escalating (config rule) %s -> %s on %s",
                            item.id, current.name, next_fetcher.name,
                            outcome.error_type.value,
                        )
                    current = next_fetcher

            logger.warning(
                "item=%s: fetch_exhausted after adapters=%s",
                item.id, [f.name for f in self.fetchers if id(f) in visited],
            )
            item.status = ItemStatus.FETCH_EXHAUSTED
            await self.registry.upsert(item)
            return last_error or RetrievalError(
                error_type=ErrorType.UNKNOWN,
                message="No fetchers configured",
                provider_used="none",
            )

    async def _fetch_with_retry(
        self, fetcher: FetcherProtocol, url: str
    ) -> RetrievalResult | RetrievalError:
        """Retry the *same* adapter on a retryable error before handing
        control back to the escalation logic — a 429/timeout should not
        immediately burn an escalation hop (design spec §9, Reliability).
        """
        attempt = 0
        outcome = await fetcher.fetch(url)
        while (
            isinstance(outcome, RetrievalError)
            and outcome.error_type in RETRYABLE_ERRORS
            and attempt < self.config.retry_attempts
        ):
            backoff = self.config.retry_backoff_base_s * (2**attempt)
            logger.debug(
                "fetcher=%s: retry %d/%d after %s in %.2fs",
                fetcher.name, attempt + 1, self.config.retry_attempts,
                outcome.error_type.value, backoff,
            )
            await self._sleep(backoff)
            attempt += 1
            outcome = await fetcher.fetch(url)
        return outcome

    async def _run_parser(
        self, parser: ParserProtocol, fetch_result: RetrievalResult
    ) -> RetrievalResult | RetrievalError:
        if fetch_result.raw_bytes is None:
            return RetrievalError(
                error_type=ErrorType.UNSUPPORTED_FORMAT,
                message="Fetcher result had no raw_bytes to hand to Parser",
                provider_used=parser.name,
            )
        return await parser.parse(fetch_result.raw_bytes, fetch_result.content_type)

    # ---- Track B: discovery -------------------------------------------------

    async def discover_source(
        self, item: ResolvableItem
    ) -> Candidate | None:
        """Run the Searcher chain for `item`. Applies the merge rules
        (design spec §3):

        - no prior source -> candidate becomes the source, item goes to
          PENDING_REVIEW, caller may re-enter Track A
        - a source already exists -> candidate is staged in
          `candidate_sources`, never auto-promoted
        - a previously-seen URL -> discarded silently

        Returns the first trusted, non-duplicate candidate, or None if
        nothing usable was found (item -> UNRESOLVED).
        """
        async with self._lock_for(item.id):
            for searcher in self.searchers:
                candidates = await searcher.search(
                    item.query_hint, n=self.config.candidate_count
                )
                for candidate in candidates:
                    if candidate.url in item.discovered_urls_seen:
                        continue  # duplicate of a previous discovery
                    if not await self.trust.is_trusted(candidate):
                        continue

                    item.discovered_urls_seen.add(candidate.url)
                    if item.current_sources:
                        item.candidate_sources.append(candidate.url)
                        logger.info(
                            "item=%s: alternate source staged via searcher=%s "
                            "(existing source kept, review required)",
                            item.id, searcher.name,
                        )
                    else:
                        item.current_sources.append(candidate.url)
                        item.status = ItemStatus.PENDING_REVIEW
                        logger.info(
                            "item=%s: new source discovered via searcher=%s, "
                            "pending_review",
                            item.id, searcher.name,
                        )
                    await self.registry.upsert(item)
                    return candidate

            logger.info("item=%s: no trusted candidate found, unresolved", item.id)
            item.status = ItemStatus.UNRESOLVED
            await self.registry.upsert(item)
            return None

    async def resolve(
        self, item: ResolvableItem
    ) -> RetrievalResult | RetrievalError | None:
        """Convenience entrypoint wiring Track B into Track A.

        If the item has no known source, discover one first. What happens
        next depends on `config.require_review` (default True, matching
        design principle 5 — "nothing auto-promotes"):

        - `require_review=True` (default): a freshly-promoted new source
          is left at PENDING_REVIEW and NOT auto-fetched — a human/process
          must approve it, then call `resolve_known_source()` explicitly.
        - `require_review=False`: an explicit opt-in for fully-automated
          pipelines — a freshly-promoted new source is fetched immediately.

        An alternate source staged alongside an existing one is never
        auto-fetched either way — it always waits for review, per the
        merge rules.
        """
        if item.current_sources:
            return await self.resolve_known_source(item)

        candidate = await self.discover_source(item)
        if candidate is None:
            return None
        if item.status == ItemStatus.PENDING_REVIEW and not self.config.require_review:
            return await self.resolve_known_source(item)
        return None  # awaiting review, or staged as a candidate_source only
