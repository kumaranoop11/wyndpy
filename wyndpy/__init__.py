"""Wyndpy — generic, pluggable content-retrieval library.

Common symbols are re-exported here for convenience:

    from wyndpy import Router, RouterConfig, ResolvableItem, load_policy, build_router

Everything is still importable from its actual submodule too
(`wyndpy.core.router.Router`, etc.) — this top-level surface is a
convenience, not the only way in, matching the "everything usable
standalone" design principle.
"""
from __future__ import annotations

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _version

from wyndpy.core.escalation import EscalationRule
from wyndpy.core.item import ItemStatus, ResolvableItem
from wyndpy.core.results import Candidate, ErrorType, RetrievalError, RetrievalResult
from wyndpy.core.router import Router, RouterConfig
from wyndpy.factory import build_router, build_scheduler
from wyndpy.policy import Policy, PolicyError, load_policy

try:
    __version__ = _version("wyndpy")
except PackageNotFoundError:
    # editable/dev checkout without an installed metadata record
    __version__ = "0.0.0+unknown"

__all__ = [
    "__version__",
    "Router",
    "RouterConfig",
    "ResolvableItem",
    "ItemStatus",
    "RetrievalResult",
    "RetrievalError",
    "Candidate",
    "ErrorType",
    "EscalationRule",
    "Policy",
    "PolicyError",
    "load_policy",
    "build_router",
    "build_scheduler",
]
