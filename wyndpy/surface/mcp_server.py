"""Exposes Wyndpy adapters as MCP tools.

Uses the same schema_for() generator as the native tool-call surface —
one definition per adapter method, two thin wrappers on top of it.

This is a skeleton: wire up an actual MCP server SDK (e.g. the official
`mcp` Python package) to register these tools and handle transport.
"""
from __future__ import annotations

from typing import Any

from wyndpy.surface.tool_schema import schema_for


class AdapterToolRegistry:
    """Collects adapters and exposes them as (schema, handler) pairs an
    MCP server implementation can register."""

    def __init__(self) -> None:
        self._tools: dict[str, tuple[dict, Any]] = {}

    def register_fetch(self, adapter) -> None:
        schema = schema_for(adapter.fetch, name=f"fetch_via_{adapter.name}")
        self._tools[schema["name"]] = (schema, adapter.fetch)

    def register_search(self, adapter) -> None:
        schema = schema_for(adapter.search, name=f"search_via_{adapter.name}")
        self._tools[schema["name"]] = (schema, adapter.search)

    def register_parse(self, adapter) -> None:
        schema = schema_for(adapter.parse, name=f"parse_via_{adapter.name}")
        self._tools[schema["name"]] = (schema, adapter.parse)

    def schemas(self) -> list[dict]:
        return [schema for schema, _ in self._tools.values()]

    async def call(self, tool_name: str, **kwargs) -> Any:
        _, handler = self._tools[tool_name]
        return await handler(**kwargs)
