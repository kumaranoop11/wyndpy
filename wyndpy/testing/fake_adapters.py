"""Fake adapters — deterministic, no network. One per role.

Mirrors a null-provider pattern: CI and unit tests depend only on these,
never on live Firecrawl/Exa/LlamaParse/httpx. Configure canned responses
per test rather than hitting a real API.
"""
from __future__ import annotations

from wyndpy.core.results import Candidate, RetrievalError, RetrievalResult


class FakeFetcher:
    name = "fake_fetcher"

    def __init__(self, responses: dict[str, RetrievalResult | RetrievalError]) -> None:
        self.responses = responses
        self.calls: list[str] = []

    async def fetch(self, url: str) -> RetrievalResult | RetrievalError:
        self.calls.append(url)
        return self.responses[url]


class FakeSearcher:
    name = "fake_searcher"

    def __init__(self, responses: dict[str, list[Candidate]]) -> None:
        self.responses = responses
        self.calls: list[str] = []

    async def search(self, query: str, n: int = 10) -> list[Candidate]:
        self.calls.append(query)
        return self.responses.get(query, [])[:n]


class FakeParser:
    name = "fake_parser"

    def __init__(self, response: RetrievalResult | RetrievalError) -> None:
        self.response = response
        self.calls = 0

    async def parse(self, data: bytes, mime_type: str) -> RetrievalResult | RetrievalError:
        self.calls += 1
        return self.response
