"""Postgres RegistryProtocol implementation — stub.

Wire this up with your project's own DB access layer (SQLAlchemy, asyncpg,
etc.) — Wyndpy doesn't impose an ORM. Only the protocol shape matters.
"""
from __future__ import annotations

from wyndpy.core.item import ResolvableItem


class PostgresRegistry:
    def __init__(self, dsn: str) -> None:
        self.dsn = dsn
        # TODO: initialize connection pool

    async def get(self, item_id: str) -> ResolvableItem | None:
        raise NotImplementedError

    async def upsert(self, item: ResolvableItem) -> None:
        raise NotImplementedError

    async def list_pending_discovery(self) -> list[ResolvableItem]:
        raise NotImplementedError
