"""Escalation rules — the config-driven mapping the router actually walks.

Defined once in core (not in policy.py) so both the policy loader and the
router share the same type, instead of the router re-implementing its own
hardcoded notion of "which errors are escalatable."
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EscalationRule:
    trigger: str          # an ErrorType value (e.g. "empty_shell") or
                           # "content_type=<mime>" for a content-type trigger
    to: str                # adapter name to escalate to
    from_: str | None = None  # adapter name this rule applies from;
                               # None means "applies from any adapter"


def content_type_trigger(rule: EscalationRule) -> str | None:
    """Return the mime type this rule triggers on, or None if it's an
    error-type trigger instead."""
    if rule.trigger.startswith("content_type="):
        return rule.trigger.split("=", 1)[1]
    return None
