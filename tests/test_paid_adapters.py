import asyncio

import pytest

from wyndpy.core.results import ErrorType, RetrievalResult
from wyndpy.fetch.firecrawl_adapter import FirecrawlFetcher
from wyndpy.parse.llamaparse_adapter import LlamaParseParser
from wyndpy.search.exa_adapter import ExaSearcher, SearchFailedError


def test_firecrawl_hashes_markdown_and_skips_network():
    async def scrape(url: str) -> dict:
        assert url == "https://docs.example.com/page"
        return {"markdown": "# ports\n64"}

    async def run() -> None:
        fetcher = FirecrawlFetcher(
            api_key="k",
            allowlist_domains=["docs.example.com"],
            scrape=scrape,
        )
        result = await fetcher.fetch("https://docs.example.com/page")
        assert isinstance(result, RetrievalResult)
        assert result.provider_used == "firecrawl"
        assert result.content == "# ports\n64"
        assert result.content_hash == RetrievalResult.hash_body(b"# ports\n64")

    asyncio.run(run())


def test_firecrawl_rejects_off_allowlist_and_missing_key():
    async def run() -> None:
        blocked = await FirecrawlFetcher(
            api_key="k",
            allowlist_domains=["docs.example.com"],
        ).fetch("https://evil.example/page")
        assert blocked.error_type is ErrorType.FORBIDDEN_URL

        missing = await FirecrawlFetcher(
            api_key="",
            allowlist_domains=["docs.example.com"],
        ).fetch("https://docs.example.com/page")
        assert missing.error_type is ErrorType.UNKNOWN

        loopback = await FirecrawlFetcher(
            api_key="k",
            allowlist_domains=["127.0.0.1"],
        ).fetch("https://127.0.0.1/page")
        assert loopback.error_type is ErrorType.FORBIDDEN_URL

    asyncio.run(run())


def test_exa_maps_hits_and_missing_key_is_empty():
    async def search_fn(query: str, n: int) -> list[dict]:
        assert query == "NVIDIA SN5600"
        assert n == 3
        return [
            {"url": "https://docs.nvidia.com/sn5600", "title": "SN5600", "score": 0.9},
            {"url": "", "title": "skip"},
        ]

    async def run() -> None:
        hits = await ExaSearcher(
            api_key="k",
            domain_allowlist=["docs.nvidia.com"],
            search_fn=search_fn,
        ).search("NVIDIA SN5600", n=3)
        assert [item.url for item in hits] == ["https://docs.nvidia.com/sn5600"]
        assert hits[0].snippet == "SN5600"
        async def off_allowlist(query: str, n: int) -> list[dict]:
            return [{"url": "https://evil.example/x", "title": "nope", "score": 1.0}]

        dropped = await ExaSearcher(
            api_key="k",
            domain_allowlist=["docs.nvidia.com"],
            search_fn=off_allowlist,
        ).search("q")
        assert dropped == []
        assert await ExaSearcher(api_key="").search("q") == []

        async def boom(query: str, n: int) -> list[dict]:
            raise ValueError("exa down")

        with pytest.raises(SearchFailedError):
            await ExaSearcher(
                api_key="k",
                domain_allowlist=["docs.nvidia.com"],
                search_fn=boom,
            ).search("q")

    asyncio.run(run())


def test_llamaparse_hashes_pdf_bytes_not_markdown():
    pdf = b"%PDF-1.4 fake"

    async def parse_fn(data: bytes, mime_type: str) -> str:
        assert data == pdf
        assert "pdf" in mime_type
        return "| ports | 64 |"

    async def run() -> None:
        result = await LlamaParseParser(api_key="k", parse_fn=parse_fn).parse(
            pdf, "application/pdf"
        )
        assert isinstance(result, RetrievalResult)
        assert result.content == "| ports | 64 |"
        assert result.content_hash == RetrievalResult.hash_body(pdf)
        assert result.raw_bytes == pdf

        empty = await LlamaParseParser(api_key="").parse(b"", "application/pdf")
        assert empty.error_type is ErrorType.UNSUPPORTED_FORMAT

    asyncio.run(run())
