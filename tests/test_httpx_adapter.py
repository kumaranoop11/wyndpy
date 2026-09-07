import asyncio
import time

import httpx

from wyndpy.core.results import ErrorType, RetrievalError
from wyndpy.fetch.httpx_adapter import HttpxFetcher, _is_private_host


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


def test_empty_allowlist_rejects_public_https():
    async def run():
        fetcher = HttpxFetcher()
        result = await fetcher.fetch("https://example.com")
        assert isinstance(result, RetrievalError)
        assert result.error_type == ErrorType.FORBIDDEN_URL
        await fetcher.close()

    asyncio.run(run())


def test_private_ip_literal_is_rejected():
    assert _is_private_host("127.0.0.1") is True
    assert _is_private_host("10.0.0.1") is True
    assert _is_private_host("8.8.8.8") is False


def test_private_host_dns_timeout_does_not_hang(monkeypatch):
    def _slow(_host: str) -> str:
        time.sleep(1)
        return "8.8.8.8"

    monkeypatch.setattr(
        "wyndpy.fetch.httpx_adapter.socket.gethostbyname", _slow
    )
    monkeypatch.setattr("wyndpy.fetch.httpx_adapter._DNS_TIMEOUT_S", 0.1)
    started = time.monotonic()
    assert _is_private_host("example.com") is False
    assert time.monotonic() - started < 0.8
