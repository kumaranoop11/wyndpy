"""Direct call surface — plain Python import, no policy/router required.

`import wyndpy.fetch.httpx_adapter` and call `.fetch()` directly if that's
all a project needs. This module adds nothing except a sync convenience
wrapper for callers that aren't already in an async context.
"""
from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any, TypeVar

T = TypeVar("T")


def run_sync(coro: Coroutine[Any, Any, T]) -> T:
    """Run an async adapter/router call from sync code.

    Not for use inside an already-running event loop (e.g. inside an
    async web handler) — call the async method directly there instead.
    """
    return asyncio.run(coro)
