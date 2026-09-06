"""Wyndpy — generic, pluggable content-retrieval library.

Common symbols are re-exported here for convenience:

    from wyndpy import Router, load_policy, build_router, FetcherProtocol

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
from wyndpy.fetch.protocol import FetcherProtocol
from wyndpy.parse.protocol import ParserProtocol
from wyndpy.policy import Policy, PolicyError, load_policy
from wyndpy.registry.protocol import RegistryProtocol
from wyndpy.scheduling.protocol import SchedulingProtocol
from wyndpy.search.protocol import SearcherProtocol
from wyndpy.surface.direct import run_sync
from wyndpy.trust.protocol import TrustStrategy

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
    "FetcherProtocol",
    "SearcherProtocol",
    "ParserProtocol",
    "RegistryProtocol",
    "TrustStrategy",
    "SchedulingProtocol",
    "run_sync",
]
