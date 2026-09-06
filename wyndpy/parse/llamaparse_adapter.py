"""LlamaParse Parser adapter — document-role adapter, PDFs/tables in particular.

Triggered by the router on content_type == pdf, never on a plain HTML miss
(that's the Fetcher escalation path, a separate role).
"""
from __future__ import annotations

from wyndpy.core.results import RetrievalError, RetrievalResult


class LlamaParseParser:
    """ParserProtocol implementation backed by the LlamaParse API."""

    name = "llamaparse"

    def __init__(self, api_key: str, timeout_s: float = 60.0) -> None:
        self.api_key = api_key
        self.timeout_s = timeout_s

    async def parse(self, data: bytes, mime_type: str) -> RetrievalResult | RetrievalError:
        # TODO: submit `data` to LlamaParse, poll for completion, retrieve
        # markdown output preserving table structure. Wrap into:
        #   RetrievalResult(content=..., content_type="text/markdown",
        #                    content_hash=RetrievalResult.hash_body(data),
        #                    provider_used=self.name, source_url=...)
        raise NotImplementedError(
            "Wire up the LlamaParse API call here; adapter shape mirrors "
            "the other roles' adapters."
        )
