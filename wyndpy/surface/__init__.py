"""Call surfaces that wrap the same adapter methods (design spec §6)."""

from wyndpy.surface.direct import run_sync
from wyndpy.surface.mcp_server import AdapterToolRegistry
from wyndpy.surface.tool_schema import schema_for

__all__ = ["AdapterToolRegistry", "run_sync", "schema_for"]
