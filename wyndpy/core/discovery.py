"""Adapter discovery via Python entry points.

A third-party package can ship a new Fetcher/Searcher/Parser and register
it under one of the `wyndpy.fetch` / `wyndpy.search` / `wyndpy.parse`
entry-point groups (see pyproject.toml) without touching Wyndpy itself.
Config then references it by name, same as a built-in adapter.
"""
from __future__ import annotations

from importlib.metadata import entry_points

_GROUPS = {
    "fetch": "wyndpy.fetch",
    "search": "wyndpy.search",
    "parse": "wyndpy.parse",
}


def available_adapters(role: str) -> dict[str, str]:
    """Return {adapter_name: import_target} for every adapter registered
    under a role, built-in or third-party."""
    group = _GROUPS[role]
    return {ep.name: ep.value for ep in entry_points(group=group)}


def load_adapter_class(role: str, name: str):
    """Import and return the adapter class registered under `name` for `role`."""
    group = _GROUPS[role]
    for ep in entry_points(group=group):
        if ep.name == name:
            return ep.load()
    raise KeyError(
        f"No adapter named {name!r} registered for role {role!r}. "
        f"Available: {sorted(available_adapters(role))}"
    )
