import asyncio

from wyndpy.core.item import ItemStatus, ResolvableItem
from wyndpy.core.results import Candidate, ErrorType, RetrievalError, RetrievalResult
from wyndpy.core.router import Router, RouterConfig
from wyndpy.registry.memory_adapter import MemoryRegistry
from wyndpy.testing.fake_adapters import FakeFetcher, FakeSearcher
from wyndpy.trust.allowlist import AllowlistTrust


def test_fast_path_resolves_on_first_fetcher():
    async def run():
        item = ResolvableItem(
            id="sku-1", query_hint="widget spec", current_sources=["https://x.test/a"]
        )
        good = RetrievalResult(
            content="<html>...</html>",
            content_type="text/html",
            source_url="https://x.test/a",
            content_hash="deadbeef",
            provider_used="fake_fetcher",
        )
        fetcher = FakeFetcher({"https://x.test/a": good})
        registry = MemoryRegistry()
        router = Router(
            fetchers=[fetcher],
            searchers=[],
            parsers=[],
            trust=AllowlistTrust(allow=["x.test"]),
            registry=registry,
        )

        result = await router.resolve_known_source(item)
        assert isinstance(result, RetrievalResult)
        assert item.status == ItemStatus.RESOLVED
        assert fetcher.calls == ["https://x.test/a"]

    asyncio.run(run())


def test_fast_path_escalates_on_empty_shell_then_exhausts():
    async def run():
        item = ResolvableItem(
            id="sku-2", query_hint="widget spec", current_sources=["https://x.test/b"]
        )
        empty_shell = RetrievalError(
            error_type=ErrorType.EMPTY_SHELL, message="js shell", provider_used="f1"
        )
        also_fails = RetrievalError(
            error_type=ErrorType.EMPTY_SHELL, message="still empty", provider_used="f2"
        )
        f1 = FakeFetcher({"https://x.test/b": empty_shell})
        f2 = FakeFetcher({"https://x.test/b": also_fails})
        registry = MemoryRegistry()
        router = Router(
            fetchers=[f1, f2],
            searchers=[],
            parsers=[],
            trust=AllowlistTrust(),
            registry=registry,
        )

        result = await router.resolve_known_source(item)
        assert isinstance(result, RetrievalError)
        assert item.status == ItemStatus.FETCH_EXHAUSTED
        assert f1.calls == ["https://x.test/b"]
        assert f2.calls == ["https://x.test/b"]  # escalation actually happened

    asyncio.run(run())


def test_discovery_returns_first_trusted_candidate():
    async def run():
        item = ResolvableItem(id="sku-3", query_hint="new widget datasheet")
        candidates = [
            Candidate(url="https://untrusted.test/x", relevance_score=0.9, snippet="..."),
            Candidate(url="https://vendor.test/spec", relevance_score=0.8, snippet="..."),
        ]
        searcher = FakeSearcher({"new widget datasheet": candidates})
        registry = MemoryRegistry()
        router = Router(
            fetchers=[],
            searchers=[searcher],
            parsers=[],
            trust=AllowlistTrust(allow=["vendor.test"]),
            registry=registry,
            config=RouterConfig(candidate_count=10),
        )

        result = await router.discover_source(item)
        assert result is not None
        assert result.url == "https://vendor.test/spec"

    asyncio.run(run())


def test_discovery_leaves_item_unresolved_when_nothing_trusted():
    async def run():
        item = ResolvableItem(id="sku-4", query_hint="obscure widget")
        searcher = FakeSearcher(
            {
                "obscure widget": [
                    Candidate(url="https://random.test/x", relevance_score=0.5, snippet="")
                ]
            }
        )
        registry = MemoryRegistry()
        router = Router(
            fetchers=[],
            searchers=[searcher],
            parsers=[],
            trust=AllowlistTrust(allow=["vendor.test"]),  # random.test won't match
            registry=registry,
        )

        result = await router.discover_source(item)
        assert result is None
        assert item.status == ItemStatus.UNRESOLVED

    asyncio.run(run())
