"""Fetch-role protocol and the built-in httpx adapter."""

from wyndpy.fetch.httpx_adapter import HttpxFetcher
from wyndpy.fetch.protocol import FetcherProtocol

__all__ = ["FetcherProtocol", "HttpxFetcher"]
