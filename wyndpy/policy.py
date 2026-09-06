"""Loads and validates a project's policy.yaml.

This file is the entire integration surface for a new project — see the
design spec §4 for the full schema and an annotated example.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import yaml

from wyndpy.core.escalation import EscalationRule

SUPPORTED_SCHEMA_VERSIONS = {1}


class PolicyError(Exception):
    pass


@dataclass
class Policy:
    schema_version: int
    roles: dict[str, list[str]]
    candidate_count: int = 10
    escalation_rules: list[EscalationRule] = field(default_factory=list)
    discovery: dict = field(default_factory=dict)
    trust_strategy: str = "allowlist"
    trust_allow: list[str] = field(default_factory=list)
    require_review: bool = True
    unresolved_handling: str = "leave_unresolved"
    registry_backend: str = "memory"
    scheduling_backend: str = "cron"
    cost_caps: dict[str, str] = field(default_factory=dict)
    rate_limits: dict[str, str] = field(default_factory=dict)


def load_policy(path: str) -> Policy:
    try:
        with open(path) as f:
            raw = yaml.safe_load(f)
    except FileNotFoundError as exc:
        raise PolicyError(f"Policy file not found: {path}") from exc
    except yaml.YAMLError as exc:
        raise PolicyError(f"Policy file is not valid YAML ({path}): {exc}") from exc

    if not isinstance(raw, dict):
        raise PolicyError(
            f"Policy file must parse to a mapping at the top level ({path}); "
            f"got {type(raw).__name__}"
        )

    version = raw.get("schema_version")
    if version not in SUPPORTED_SCHEMA_VERSIONS:
        raise PolicyError(
            f"Unsupported schema_version={version!r}; this Wyndpy version "
            f"supports {sorted(SUPPORTED_SCHEMA_VERSIONS)}"
        )

    roles = raw.get("roles", {})
    if not roles.get("fetch"):
        raise PolicyError("policy.yaml must define at least one `roles.fetch` adapter")

    rules = []
    for i, r in enumerate(raw.get("escalation_rules", [])):
        missing = [k for k in ("trigger", "to") if k not in r]
        if missing:
            raise PolicyError(
                f"escalation_rules[{i}] is missing required key(s) {missing}: {r!r}"
            )
        rules.append(EscalationRule(trigger=r["trigger"], to=r["to"], from_=r.get("from")))

    trust = raw.get("trust", {})

    return Policy(
        schema_version=version,
        roles=roles,
        candidate_count=raw.get("search", {}).get("candidate_count", 10),
        escalation_rules=rules,
        discovery=raw.get("discovery", {}),
        trust_strategy=trust.get("strategy", "allowlist"),
        trust_allow=trust.get("allow", []),
        require_review=trust.get("require_review", True),
        unresolved_handling=raw.get("unresolved_handling", "leave_unresolved"),
        registry_backend=raw.get("registry_backend", "memory"),
        scheduling_backend=raw.get("scheduling_backend", "cron"),
        cost_caps=raw.get("cost_caps", {}),
        rate_limits=raw.get("rate_limits", {}),
    )
