"""In-memory RegistryProtocol implementation.

Default backend for tests and small/standalone deployments. A project
wanting persistence swaps in postgres_adapter.py (or its own) via config —
no router or core code changes required.
"""
from __future__ import annotations

from wyndpy.core.item import ItemStatus, ResolvableItem


class MemoryRegistry:
    def __init__(self) -> None:
        self._items: dict[str, ResolvableItem] = {}

    async def get(self, item_id: str) -> ResolvableItem | None:
        return self._items.get(item_id)

    async def upsert(self, item: ResolvableItem) -> None:
        self._items[item.id] = item

    async def list_pending_discovery(self) -> list[ResolvableItem]:
        return [
            i
            for i in self._items.values()
            if i.status == ItemStatus.PENDING_DISCOVERY
        ]
