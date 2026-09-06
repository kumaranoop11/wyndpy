import pytest

from wyndpy.core.escalation import EscalationRule
from wyndpy.factory import build_router, build_scheduler
from wyndpy.policy import Policy, PolicyError
from wyndpy.registry.memory_adapter import MemoryRegistry
from wyndpy.scheduling.cron_adapter import CronScheduler
from wyndpy.scheduling.event_adapter import EventScheduler
from wyndpy.testing import FakeFetcher
from wyndpy.trust.allowlist import AllowlistTrust


def _base_policy(**overrides) -> Policy:
    defaults = dict(
        schema_version=1,
        roles={"fetch": ["httpx"]},
        candidate_count=10,
        escalation_rules=[EscalationRule(trigger="empty_shell", from_="httpx", to="firecrawl")],
        trust_strategy="allowlist",
        trust_allow=["example.com"],
        require_review=True,
        registry_backend="memory",
        scheduling_backend="cron",
    )
    defaults.update(overrides)
    return Policy(**defaults)


def test_build_router_wires_fetchers_by_name():
    router = build_router(_base_policy())
    assert [f.name for f in router.fetchers] == ["httpx"]
    assert router.searchers == []
    assert router.parsers == []


def test_build_router_passes_escalation_rules_through():
    policy = _base_policy()
    router = build_router(policy)
    assert router.escalation_rules == policy.escalation_rules
    # and the router actually indexed it, not just stored it verbatim
    assert ("httpx", "empty_shell") in router._error_escalations


def test_build_router_passes_credentials_to_adapter_constructor():
    router = build_router(
        _base_policy(),
        credentials={"httpx": {"allowlist_domains": ["only-this.example.com"]}},
    )
    assert router.fetchers[0].allowlist_domains == ["only-this.example.com"]


def test_build_router_wires_trust_allow_into_httpx_when_credentials_omit_it():
    router = build_router(_base_policy(trust_allow=["*.vendor.test"]))
    assert router.fetchers[0].allowlist_domains == ["vendor.test"]


def test_build_router_httpx_empty_allowlist_raises():
    with pytest.raises(PolicyError, match="non-empty allowlist"):
        build_router(_base_policy(trust_allow=[]))


def test_build_router_accepts_injected_registry_and_trust():
    class _Reg:
        async def get(self, item_id: str):
            return None

        async def upsert(self, item) -> None:
            return None

        async def list_pending_discovery(self):
            return []

    class _Trust:
        async def is_trusted(self, candidate) -> bool:
            return True

    registry = _Reg()
    trust = _Trust()
    router = build_router(
        _base_policy(trust_strategy="reputation"),
        registry=registry,
        trust=trust,
    )
    assert router.registry is registry
    assert router.trust is trust


def test_build_router_accepts_prebuilt_fetchers():
    fake = FakeFetcher(responses={})
    router = build_router(_base_policy(trust_allow=[]), fetchers=[fake])
    assert router.fetchers == [fake]


def test_build_router_refuses_stub_adapters():
    policy = _base_policy(roles={"fetch": ["httpx", "firecrawl"]})
    with pytest.raises(PolicyError, match="stub"):
        build_router(policy, credentials={"firecrawl": {"api_key": "k"}})


def test_build_router_allow_stubs_constructs_firecrawl():
    policy = _base_policy(roles={"fetch": ["httpx", "firecrawl"]})
    router = build_router(
        policy,
        credentials={"firecrawl": {"api_key": "k"}},
        allow_stubs=True,
    )
    assert [f.name for f in router.fetchers] == ["httpx", "firecrawl"]


def test_build_router_uses_allowlist_trust_from_policy():
    router = build_router(_base_policy(trust_allow=["vendor.test"]))
    assert isinstance(router.trust, AllowlistTrust)
    assert router.trust.allow == ["vendor.test"]


def test_build_router_uses_memory_registry_by_default():
    router = build_router(_base_policy())
    assert isinstance(router.registry, MemoryRegistry)


def test_build_router_unknown_trust_strategy_raises():
    with pytest.raises(PolicyError):
        build_router(_base_policy(trust_strategy="reputation"))


def test_build_router_postgres_is_refused_as_stub():
    with pytest.raises(PolicyError, match="stub"):
        build_router(_base_policy(registry_backend="postgres"))


def test_build_router_postgres_without_dsn_raises_when_stubs_allowed():
    with pytest.raises(PolicyError, match="dsn"):
        build_router(_base_policy(registry_backend="postgres"), allow_stubs=True)


def test_build_router_config_carries_candidate_count_and_require_review():
    router = build_router(_base_policy(candidate_count=25, require_review=False))
    assert router.config.candidate_count == 25
    assert router.config.require_review is False


def test_build_router_missing_adapter_credentials_raises_clear_policy_error():
    """Constructing an adapter with missing required kwargs (e.g. no
    api_key) should surface as a PolicyError naming the adapter and role,
    not a raw TypeError from the adapter's __init__."""
    policy = _base_policy(roles={"fetch": ["httpx", "firecrawl"]})
    with pytest.raises(PolicyError, match="firecrawl.*fetch"):
        build_router(policy, allow_stubs=True)


def test_build_scheduler_cron():
    assert isinstance(build_scheduler(_base_policy(scheduling_backend="cron")), CronScheduler)


def test_build_scheduler_event():
    assert isinstance(build_scheduler(_base_policy(scheduling_backend="event")), EventScheduler)


def test_build_scheduler_unknown_backend_raises():
    with pytest.raises(PolicyError):
        build_scheduler(_base_policy(scheduling_backend="something_else"))


def test_public_exports_include_protocols_and_fakes():
    import wyndpy
    from wyndpy.testing import FakeFetcher, FakeParser, FakeSearcher

    assert wyndpy.FetcherProtocol is not None
    assert wyndpy.RegistryProtocol is not None
    assert wyndpy.TrustStrategy is not None
    assert FakeFetcher is not None
    assert FakeSearcher is not None
    assert FakeParser is not None
