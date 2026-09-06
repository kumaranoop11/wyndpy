"""RegistryProtocol — persists ResolvableItems and their known sources."""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from wyndpy.core.item import ResolvableItem


@runtime_checkable
class RegistryProtocol(Protocol):
    async def get(self, item_id: str) -> ResolvableItem | None: ...

    async def upsert(self, item: ResolvableItem) -> None: ...

    async def list_pending_discovery(self) -> list[ResolvableItem]: ...
