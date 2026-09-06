import asyncio

import httpx

from wyndpy.fetch.httpx_adapter import HttpxFetcher


def test_client_is_created_lazily_and_reused_across_calls():
    async def run():
        fetcher = HttpxFetcher(allowlist_domains=["example.com"])
        assert fetcher._client is None  # not created until first fetch

        await fetcher.fetch("https://example.com")
        client_after_first = fetcher._client
        assert client_after_first is not None

        await fetcher.fetch("https://example.com")
        # same client instance reused — no new TCP/TLS handshake per call
        assert fetcher._client is client_after_first

        await fetcher.close()
        assert fetcher._client is None

    asyncio.run(run())


def test_async_context_manager_closes_client():
    async def run():
        async with HttpxFetcher(allowlist_domains=["example.com"]) as fetcher:
            await fetcher.fetch("https://example.com")
            assert fetcher._client is not None
        assert fetcher._client is None  # closed on exit

    asyncio.run(run())


def test_injected_client_is_not_owned_or_closed():
    async def run():
        injected = httpx.AsyncClient()
        fetcher = HttpxFetcher(allowlist_domains=["example.com"], client=injected)
        assert fetcher._owns_client is False

        await fetcher.fetch("https://example.com")
        await fetcher.close()
        # close() must not touch a client the caller injected/owns
        assert fetcher._client is injected
        assert injected.is_closed is False

        await injected.aclose()

    asyncio.run(run())
