"""Registry protocol and the in-memory backend."""

from wyndpy.registry.memory_adapter import MemoryRegistry
from wyndpy.registry.protocol import RegistryProtocol

__all__ = ["MemoryRegistry", "RegistryProtocol"]
