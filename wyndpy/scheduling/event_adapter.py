"""Event-triggered scheduling adapter — for e.g. re-discovery on fetch failure."""
from __future__ import annotations

import asyncio

from wyndpy.scheduling.protocol import Job


class EventScheduler:
    def __init__(self) -> None:
        self._jobs: dict[str, list[Job]] = {}

    def register(self, job: Job, cadence_or_trigger: str) -> None:
        self._jobs.setdefault(cadence_or_trigger, []).append(job)

    async def fire(self, trigger: str) -> None:
        """Run every job registered under this trigger, concurrently."""
        jobs = self._jobs.get(trigger, [])
        await asyncio.gather(*(job() for job in jobs))
