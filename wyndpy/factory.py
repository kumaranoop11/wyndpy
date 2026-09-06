"""Builds a Router from a Policy — the piece that makes config actually
drive behavior, rather than being parsed and then ignored.

Usage:
    policy = load_policy("policy.yaml")
    router = build_router(policy, credentials={"httpx": {"allowlist_domains": [...]}})

    # A consuming project injects its own store / trust / adapters:
    router = build_router(policy, registry=MyRegistry(), trust=MyTrust())
"""
from __future__ import annotations

from typing import cast

from wyndpy.core.discovery import load_adapter_class
from wyndpy.core.router import Router, RouterConfig
from wyndpy.fetch.protocol import FetcherProtocol
from wyndpy.parse.protocol import ParserProtocol
from wyndpy.policy import Policy, PolicyError
from wyndpy.registry.memory_adapter import MemoryRegistry
from wyndpy.registry.protocol import RegistryProtocol
from wyndpy.scheduling.cron_adapter import CronScheduler
from wyndpy.scheduling.event_adapter import EventScheduler
from wyndpy.search.protocol import SearcherProtocol
from wyndpy.trust.allowlist import AllowlistTrust
from wyndpy.trust.protocol import TrustStrategy


def _normalize_allow(domains: list[str]) -> list[str]:
    """Strip ``*.`` prefixes so policy trust.allow matches HttpxFetcher."""
    normalized: list[str] = []
    for raw in domains:
        domain = raw.lstrip("*.")
        if domain and domain not in normalized:
            normalized.append(domain)
    return normalized


def _construct(
    role: str,
    name: str,
    credentials: dict,
    *,
    allow_stubs: bool,
    trust_allow: list[str] | None = None,
):
    cls = load_adapter_class(role, name)
    if not getattr(cls, "implemented", True) and not allow_stubs:
        raise PolicyError(
            f"Adapter '{name}' for role '{role}' is a stub "
            f"({cls.__module__}.{cls.__qualname__}): the API call is not "
            f"wired yet. Leave it out of policy.roles, or pass "
            f"allow_stubs=True to construct it for tests."
        )
    kwargs = dict(credentials.get(name, {}))
    if role == "fetch" and name == "httpx" and "allowlist_domains" not in kwargs:
        kwargs["allowlist_domains"] = _normalize_allow(list(trust_allow or []))
    if role == "fetch" and name == "httpx" and not kwargs.get("allowlist_domains"):
        raise PolicyError(
            "httpx fetcher requires a non-empty allowlist. Set "
            "trust.allow in the policy, or pass "
            "credentials={'httpx': {'allowlist_domains': [...]}}."
        )
    try:
        return cls(**kwargs)
    except TypeError as exc:
        raise PolicyError(
            f"Could not construct adapter '{name}' for role '{role}' "
            f"({cls.__module__}.{cls.__qualname__}): {exc}. "
            f"Pass its required constructor arguments via "
            f"credentials={{{name!r}: {{...}}}} in build_router(policy, credentials=...)."
        ) from exc


def _instantiate_fetcher(
    name: str,
    credentials: dict,
    *,
    allow_stubs: bool,
    trust_allow: list[str],
) -> FetcherProtocol:
    return cast(
        FetcherProtocol,
        _construct(
            "fetch",
            name,
            credentials,
            allow_stubs=allow_stubs,
            trust_allow=trust_allow,
        ),
    )


def _instantiate_searcher(
    name: str, credentials: dict, *, allow_stubs: bool
) -> SearcherProtocol:
    return cast(
        SearcherProtocol,
        _construct("search", name, credentials, allow_stubs=allow_stubs),
    )


def _instantiate_parser(
    name: str, credentials: dict, *, allow_stubs: bool
) -> ParserProtocol:
    return cast(
        ParserProtocol,
        _construct("parse", name, credentials, allow_stubs=allow_stubs),
    )


def _build_trust(policy: Policy) -> TrustStrategy:
    if policy.trust_strategy == "allowlist":
        return AllowlistTrust(allow=policy.trust_allow)
    raise PolicyError(
        f"Unknown trust.strategy={policy.trust_strategy!r}; only 'allowlist' "
        f"ships built-in — pass trust= to build_router() for a custom "
        f"TrustStrategy, or construct Router() directly."
    )


def _build_registry(
    policy: Policy, credentials: dict, *, allow_stubs: bool
) -> RegistryProtocol:
    if policy.registry_backend == "memory":
        return MemoryRegistry()
    if policy.registry_backend == "postgres":
        from wyndpy.registry.postgres_adapter import PostgresRegistry

        if not getattr(PostgresRegistry, "implemented", True) and not allow_stubs:
            raise PolicyError(
                "registry_backend=postgres is a stub. Pass registry= to "
                "build_router() with your project's store, or set "
                "registry_backend=memory."
            )
        dsn = credentials.get("postgres", {}).get("dsn")
        if not dsn:
            raise PolicyError(
                "registry_backend=postgres requires credentials['postgres']['dsn']"
            )
        return PostgresRegistry(dsn=dsn)
    if policy.registry_backend == "sqlite":
        raise PolicyError(
            "registry_backend=sqlite has no built-in adapter — pass "
            "registry= to build_router() with your own RegistryProtocol."
        )
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


def build_router(
    policy: Policy,
    credentials: dict | None = None,
    *,
    registry: RegistryProtocol | None = None,
    trust: TrustStrategy | None = None,
    fetchers: list[FetcherProtocol] | None = None,
    searchers: list[SearcherProtocol] | None = None,
    parsers: list[ParserProtocol] | None = None,
    allow_stubs: bool = False,
) -> Router:
    """Construct a fully-wired Router from a Policy.

    `credentials` maps adapter name -> constructor kwargs, e.g.
    `{"httpx": {"allowlist_domains": ["vendor.example"]}}`.

    A consuming project can inject its own `registry`, `trust`, or
    prebuilt adapter lists instead of the built-in backends. Stub
    adapters (Firecrawl, Exa, LlamaParse, Postgres) are refused unless
    `allow_stubs=True`.
    """
    credentials = dict(credentials or {})

    built_fetchers = (
        fetchers
        if fetchers is not None
        else [
            _instantiate_fetcher(
                name,
                credentials,
                allow_stubs=allow_stubs,
                trust_allow=policy.trust_allow,
            )
            for name in policy.roles.get("fetch", [])
        ]
    )
    built_searchers = (
        searchers
        if searchers is not None
        else [
            _instantiate_searcher(name, credentials, allow_stubs=allow_stubs)
            for name in policy.roles.get("search", [])
        ]
    )
    built_parsers = (
        parsers
        if parsers is not None
        else [
            _instantiate_parser(name, credentials, allow_stubs=allow_stubs)
            for name in policy.roles.get("parse", [])
        ]
    )

    return Router(
        fetchers=built_fetchers,
        searchers=built_searchers,
        parsers=built_parsers,
        trust=trust if trust is not None else _build_trust(policy),
        registry=(
            registry
            if registry is not None
            else _build_registry(policy, credentials, allow_stubs=allow_stubs)
        ),
        config=RouterConfig(
            candidate_count=policy.candidate_count,
            require_review=policy.require_review,
        ),
        escalation_rules=policy.escalation_rules,
    )
