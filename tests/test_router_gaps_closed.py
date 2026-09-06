import asyncio

from wyndpy.core.escalation import EscalationRule
from wyndpy.core.item import ItemStatus, ResolvableItem
from wyndpy.core.results import (
    Candidate,
    ErrorType,
    RetrievalError,
    RetrievalResult,
)
from wyndpy.core.router import Router, RouterConfig
from wyndpy.registry.memory_adapter import MemoryRegistry
from wyndpy.testing.fake_adapters import FakeFetcher, FakeParser, FakeSearcher
from wyndpy.trust.allowlist import AllowlistTrust


async def _noop_sleep(_seconds: float) -> None:
    pass  # keep retry tests fast — no real waiting


def test_config_driven_escalation_uses_explicit_from_to():
    """Two adapters that both happen to be named the same underlying
    type should still escalate correctly when escalation_rules name them
    explicitly by adapter `.name`."""

    async def run():
        item = ResolvableItem(
            id="sku-5", query_hint="x", current_sources=["https://x.test/c"]
        )
        empty_shell = RetrievalError(
            error_type=ErrorType.EMPTY_SHELL, message="shell", provider_used="httpx"
        )
        good = RetrievalResult(
            content="ok",
            content_type="text/html",
            source_url="https://x.test/c",
            content_hash="abc123",
            provider_used="firecrawl",
        )
        httpx_like = FakeFetcher({"https://x.test/c": empty_shell})
        httpx_like.name = "httpx"
        firecrawl_like = FakeFetcher({"https://x.test/c": good})
        firecrawl_like.name = "firecrawl"

        router = Router(
            fetchers=[httpx_like, firecrawl_like],
            searchers=[],
            parsers=[],
            trust=AllowlistTrust(),
            registry=MemoryRegistry(),
            escalation_rules=[
                EscalationRule(trigger="empty_shell", from_="httpx", to="firecrawl")
            ],
        )

        result = await router.resolve_known_source(item)
        assert isinstance(result, RetrievalResult)
        assert result.provider_used == "firecrawl"
        assert item.status == ItemStatus.RESOLVED

    asyncio.run(run())


def test_config_driven_no_matching_rule_stops_without_escalating():
    async def run():
        item = ResolvableItem(
            id="sku-6", query_hint="x", current_sources=["https://x.test/d"]
        )
        not_found = RetrievalError(
            error_type=ErrorType.NOT_FOUND, message="404", provider_used="httpx"
        )
        f1 = FakeFetcher({"https://x.test/d": not_found})
        f1.name = "httpx"
        f2 = FakeFetcher({"https://x.test/d": not_found})
        f2.name = "firecrawl"

        router = Router(
            fetchers=[f1, f2],
            searchers=[],
            parsers=[],
            trust=AllowlistTrust(),
            registry=MemoryRegistry(),
            # only empty_shell escalates; not_found has no rule -> terminal
            escalation_rules=[
                EscalationRule(trigger="empty_shell", from_="httpx", to="firecrawl")
            ],
        )

        result = await router.resolve_known_source(item)
        assert isinstance(result, RetrievalError)
        assert item.status == ItemStatus.FETCH_EXHAUSTED
        assert f1.calls == ["https://x.test/d"]
        assert f2.calls == []  # never escalated — no rule matched NOT_FOUND

    asyncio.run(run())


def test_retry_recovers_before_escalating():
    async def run():
        item = ResolvableItem(
            id="sku-7", query_hint="x", current_sources=["https://x.test/e"]
        )
        timeout_err = RetrievalError(
            error_type=ErrorType.TIMEOUT, message="slow", provider_used="httpx"
        )
        good = RetrievalResult(
            content="ok",
            content_type="text/html",
            source_url="https://x.test/e",
            content_hash="hash1",
            provider_used="httpx",
        )

        # A fetcher whose first two calls time out, third succeeds.
        calls = {"n": 0}
        outcomes = [timeout_err, timeout_err, good]

        class FlakyFetcher:
            name = "httpx"

            async def fetch(self, url):
                outcome = outcomes[calls["n"]]
                calls["n"] += 1
                return outcome

        router = Router(
            fetchers=[FlakyFetcher()],
            searchers=[],
            parsers=[],
            trust=AllowlistTrust(),
            registry=MemoryRegistry(),
            config=RouterConfig(retry_attempts=2, retry_backoff_base_s=0.01),
            sleep=_noop_sleep,
        )

        result = await router.resolve_known_source(item)
        assert isinstance(result, RetrievalResult)
        assert calls["n"] == 3  # two failed attempts + one success, same adapter

    asyncio.run(run())


def test_pdf_content_type_routes_to_configured_parser():
    async def run():
        item = ResolvableItem(
            id="sku-8", query_hint="x", current_sources=["https://x.test/f.pdf"]
        )
        pdf_result = RetrievalResult(
            content="",
            content_type="application/pdf",
            source_url="https://x.test/f.pdf",
            content_hash="pdfhash",
            provider_used="httpx",
            raw_bytes=b"%PDF-1.4 fake bytes",
        )
        parsed = RetrievalResult(
            content="# Extracted table\n...",
            content_type="text/markdown",
            source_url="https://x.test/f.pdf",
            content_hash="parsedhash",
            provider_used="llamaparse",
        )
        fetcher = FakeFetcher({"https://x.test/f.pdf": pdf_result})
        fetcher.name = "httpx"
        parser = FakeParser(parsed)
        parser.name = "llamaparse"

        router = Router(
            fetchers=[fetcher],
            searchers=[],
            parsers=[parser],
            trust=AllowlistTrust(),
            registry=MemoryRegistry(),
            escalation_rules=[
                EscalationRule(
                    trigger="content_type=application/pdf",
                    from_="httpx",
                    to="llamaparse",
                )
            ],
        )

        result = await router.resolve_known_source(item)
        assert isinstance(result, RetrievalResult)
        assert result.provider_used == "llamaparse"
        assert parser.calls == 1

    asyncio.run(run())


def test_merge_rule_new_item_default_requires_review_no_auto_fetch():
    """Default require_review=True: a freshly-discovered new source is
    promoted into current_sources and marked PENDING_REVIEW, but NOT
    auto-fetched — matching design principle 5, 'nothing auto-promotes'."""

    async def run():
        item = ResolvableItem(id="sku-9", query_hint="new widget")
        candidate = Candidate(url="https://vendor.test/spec", relevance_score=0.9, snippet="")
        searcher = FakeSearcher({"new widget": [candidate]})
        fetcher = FakeFetcher({})  # should never be called

        router = Router(
            fetchers=[fetcher],
            searchers=[searcher],
            parsers=[],
            trust=AllowlistTrust(allow=["vendor.test"]),
            registry=MemoryRegistry(),
            # RouterConfig() default -> require_review=True
        )

        result = await router.resolve(item)
        assert result is None  # not auto-fetched
        assert item.current_sources == ["https://vendor.test/spec"]
        assert item.status == ItemStatus.PENDING_REVIEW
        assert fetcher.calls == []  # confirms no auto-fetch happened

    asyncio.run(run())


def test_merge_rule_new_item_opt_out_of_review_auto_fetches():
    """require_review=False is an explicit opt-in for fully-automated
    pipelines that don't want a human gate on newly-discovered sources."""

    async def run():
        item = ResolvableItem(id="sku-9b", query_hint="new widget")
        candidate = Candidate(url="https://vendor.test/spec", relevance_score=0.9, snippet="")
        searcher = FakeSearcher({"new widget": [candidate]})
        good = RetrievalResult(
            content="ok",
            content_type="text/html",
            source_url="https://vendor.test/spec",
            content_hash="h1",
            provider_used="httpx",
        )
        fetcher = FakeFetcher({"https://vendor.test/spec": good})

        router = Router(
            fetchers=[fetcher],
            searchers=[searcher],
            parsers=[],
            trust=AllowlistTrust(allow=["vendor.test"]),
            registry=MemoryRegistry(),
            config=RouterConfig(require_review=False),
        )

        result = await router.resolve(item)
        assert isinstance(result, RetrievalResult)
        assert item.status == ItemStatus.RESOLVED  # promoted, then fetched

    asyncio.run(run())


def test_merge_rule_existing_source_stages_candidate_no_auto_fetch():
    async def run():
        item = ResolvableItem(
            id="sku-10",
            query_hint="widget",
            current_sources=["https://original.test/spec"],
        )
        alt = Candidate(url="https://vendor.test/newer-spec", relevance_score=0.9, snippet="")
        searcher = FakeSearcher({"widget": [alt]})
        registry = MemoryRegistry()

        router = Router(
            fetchers=[],  # should never be called — no auto-fetch expected
            searchers=[searcher],
            parsers=[],
            trust=AllowlistTrust(allow=["vendor.test"]),
            registry=registry,
        )

        found = await router.discover_source(item)
        assert found is not None
        assert item.current_sources == ["https://original.test/spec"]  # unchanged
        assert item.candidate_sources == ["https://vendor.test/newer-spec"]

    asyncio.run(run())


def test_merge_rule_duplicate_discovery_discarded():
    async def run():
        item = ResolvableItem(id="sku-11", query_hint="widget")
        item.discovered_urls_seen.add("https://vendor.test/spec")
        seen_again = Candidate(url="https://vendor.test/spec", relevance_score=0.9, snippet="")
        fresh = Candidate(url="https://vendor.test/other", relevance_score=0.5, snippet="")
        searcher = FakeSearcher({"widget": [seen_again, fresh]})

        router = Router(
            fetchers=[],
            searchers=[searcher],
            parsers=[],
            trust=AllowlistTrust(allow=["vendor.test"]),
            registry=MemoryRegistry(),
        )

        found = await router.discover_source(item)
        assert found is not None
        assert found.url == "https://vendor.test/other"  # duplicate skipped

    asyncio.run(run())
