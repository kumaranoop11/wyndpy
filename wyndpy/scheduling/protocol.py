"""SchedulingProtocol — wires Track A / Track B to a scheduling backend."""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Protocol, runtime_checkable

Job = Callable[[], Awaitable[None]]


@runtime_checkable
class SchedulingProtocol(Protocol):
    def register(self, job: Job, cadence_or_trigger: str) -> None:
        """Wire `job` to run on the given cadence (e.g. 'monthly') or
        trigger (e.g. 'event:fetch_failure'). Interpretation of the string
        is backend-specific.
        """
        ...
