"""Builds a Router from a Policy — the piece that makes config actually
drive behavior, rather than being parsed and then ignored.

Usage:
    policy = load_policy("policy.yaml")
    router = build_router(
        policy,
        credentials={
            "firecrawl": {"api_key": "..."},
            "exa": {"api_key": "..."},
            "llamaparse": {"api_key": "..."},
        },
    )
"""
from __future__ import annotations

from typing import cast

from wyndpy.core.discovery import load_adapter_class
from wyndpy.core.router import Router, RouterConfig
from wyndpy.fetch.protocol import FetcherProtocol
from wyndpy.parse.protocol import ParserProtocol
from wyndpy.policy import Policy, PolicyError
from wyndpy.registry.memory_adapter import MemoryRegistry
from wyndpy.scheduling.cron_adapter import CronScheduler
from wyndpy.scheduling.event_adapter import EventScheduler
from wyndpy.search.protocol import SearcherProtocol
from wyndpy.trust.allowlist import AllowlistTrust


def _construct(role: str, name: str, credentials: dict):
    cls = load_adapter_class(role, name)
    kwargs = credentials.get(name, {})
    try:
        return cls(**kwargs)
    except TypeError as exc:
        raise PolicyError(
            f"Could not construct adapter '{name}' for role '{role}' "
            f"({cls.__module__}.{cls.__qualname__}): {exc}. "
            f"Pass its required constructor arguments via "
            f"credentials={{{name!r}: {{...}}}} in build_router(policy, credentials=...)."
        ) from exc


def _instantiate_fetcher(name: str, credentials: dict) -> FetcherProtocol:
    return cast(FetcherProtocol, _construct("fetch", name, credentials))


def _instantiate_searcher(name: str, credentials: dict) -> SearcherProtocol:
    return cast(SearcherProtocol, _construct("search", name, credentials))


def _instantiate_parser(name: str, credentials: dict) -> ParserProtocol:
    return cast(ParserProtocol, _construct("parse", name, credentials))


def _build_trust(policy: Policy):
    if policy.trust_strategy == "allowlist":
        return AllowlistTrust(allow=policy.trust_allow)
    raise PolicyError(
        f"Unknown trust.strategy={policy.trust_strategy!r}; only 'allowlist' "
        f"ships built-in — pass a custom TrustStrategy instance directly to "
        f"Router() instead of using build_router() for other strategies."
    )


def _build_registry(policy: Policy, credentials: dict):
    if policy.registry_backend == "memory":
        return MemoryRegistry()
    if policy.registry_backend == "postgres":
        from wyndpy.registry.postgres_adapter import PostgresRegistry

        dsn = credentials.get("postgres", {}).get("dsn")
        if not dsn:
            raise PolicyError(
                "registry_backend=postgres requires credentials['postgres']['dsn']"
            )
        return PostgresRegistry(dsn=dsn)
    raise PolicyError(f"Unknown registry_backend={policy.registry_backend!r}")


def build_scheduler(policy: Policy):
    """Return a scheduler instance matching policy.scheduling_backend.

    This only builds the scheduler — registering actual jobs (Track A's
    per-cycle fetch, Track B's discovery cadence from `policy.discovery`)
    is left to the consuming project, since the job callables themselves
    are project-specific (what "every cycle" iterates over, etc.).
    """
    if policy.scheduling_backend == "cron":
        return CronScheduler()
    if policy.scheduling_backend == "event":
        return EventScheduler()
    if policy.scheduling_backend == "background_task":
        raise PolicyError(
            "scheduling_backend=background_task has no built-in adapter — "
            "wire your framework's background-task API directly against "
            "SchedulingProtocol instead of using build_scheduler()."
        )
    raise PolicyError(f"Unknown scheduling_backend={policy.scheduling_backend!r}")


def build_router(policy: Policy, credentials: dict | None = None) -> Router:
    """Construct a fully-wired Router from a Policy.

    `credentials` maps adapter name -> constructor kwargs, e.g.
    `{"firecrawl": {"api_key": "..."}}`. Adapters needing no credentials
    (like the default httpx fetcher) can be omitted.
    """
    credentials = credentials or {}

    fetchers = [
        _instantiate_fetcher(name, credentials)
        for name in policy.roles.get("fetch", [])
    ]
    searchers = [
        _instantiate_searcher(name, credentials)
        for name in policy.roles.get("search", [])
    ]
    parsers = [
        _instantiate_parser(name, credentials)
        for name in policy.roles.get("parse", [])
    ]

    return Router(
        fetchers=fetchers,
        searchers=searchers,
        parsers=parsers,
        trust=_build_trust(policy),
        registry=_build_registry(policy, credentials),
        config=RouterConfig(
            candidate_count=policy.candidate_count,
            require_review=policy.require_review,
        ),
        escalation_rules=policy.escalation_rules,
    )
