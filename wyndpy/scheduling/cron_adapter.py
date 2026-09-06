"""Cron-style scheduling adapter — for projects driving Wyndpy from a
Makefile / system cron rather than an in-process scheduler.

register() here just records the mapping; the actual cron entry lives in
the project's crontab/CI, invoking a CLI entrypoint that calls the job.
"""
from __future__ import annotations

from wyndpy.scheduling.protocol import Job


class CronScheduler:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}

    def register(self, job: Job, cadence_or_trigger: str) -> None:
        self._jobs[cadence_or_trigger] = job

    def jobs(self) -> dict[str, Job]:
        """Expose registered jobs so a CLI entrypoint can look one up by
        cadence string and run it."""
        return dict(self._jobs)
