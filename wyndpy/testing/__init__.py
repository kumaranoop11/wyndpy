"""Deterministic adapters for consuming-project tests. No network."""

from wyndpy.testing.fake_adapters import FakeFetcher, FakeParser, FakeSearcher

__all__ = ["FakeFetcher", "FakeParser", "FakeSearcher"]
