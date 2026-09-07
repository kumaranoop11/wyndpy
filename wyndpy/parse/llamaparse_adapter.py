"""LlamaParse Parser adapter — PDFs and table-heavy documents.

Triggered by the router on content_type == pdf. ``parse_fn`` is injectable
so tests never hit the network. ``content_hash`` is SHA-256 of the PDF
bytes, not the markdown, so hash-skip stays stable across parse runs.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

import httpx

from wyndpy.core.results import ErrorType, RetrievalError, RetrievalResult

logger = logging.getLogger("wyndpy.parse.llamaparse")

LLAMA_UPLOAD_URL = "https://api.cloud.llamaindex.ai/api/parsing/upload"
DEFAULT_TIMEOUT_S = 60.0
POLL_INTERVAL_S = 1.0
MAX_POLLS = 45

ParseFn = Callable[[bytes, str], Awaitable[str]]


class LlamaParseParser:
    """ParserProtocol implementation backed by the LlamaParse API."""

    name = "llamaparse"
    implemented = True

    def __init__(
        self,
        api_key: str,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        parse_fn: ParseFn | None = None,
    ) -> None:
        self.api_key = api_key
        self.timeout_s = timeout_s
        self._parse_fn = parse_fn

    async def parse(self, data: bytes, mime_type: str) -> RetrievalResult | RetrievalError:
        if not data:
            return RetrievalError(
                error_type=ErrorType.UNSUPPORTED_FORMAT,
                message="LlamaParse received an empty body",
                provider_used=self.name,
            )
        if not self.api_key and self._parse_fn is None:
            return RetrievalError(
                error_type=ErrorType.UNKNOWN,
                message="LlamaParse API key is not set",
                provider_used=self.name,
            )
        try:
            markdown = await (
                self._parse_fn(data, mime_type)
                if self._parse_fn
                else self._parse_live(data, mime_type)
            )
        except (httpx.TimeoutException, TimeoutError):
            return RetrievalError(
                error_type=ErrorType.TIMEOUT,
                message="Timed out waiting for LlamaParse",
                provider_used=self.name,
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 429:
                return RetrievalError(
                    error_type=ErrorType.RATE_LIMITED,
                    message="429 from LlamaParse",
                    provider_used=self.name,
                )
            return RetrievalError(
                error_type=ErrorType.UNKNOWN,
                message=str(exc),
                provider_used=self.name,
            )
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            return RetrievalError(
                error_type=ErrorType.UNKNOWN,
                message=str(exc),
                provider_used=self.name,
            )
        return RetrievalResult(
            content=markdown,
            content_type="text/markdown",
            source_url="",
            content_hash=RetrievalResult.hash_body(data),
            provider_used=self.name,
            raw_bytes=data,
        )

    async def _parse_live(self, data: bytes, mime_type: str) -> str:
        headers = {"Authorization": f"Bearer {self.api_key}"}
        filename = "document.pdf" if "pdf" in mime_type else "document.bin"
        async with httpx.AsyncClient(timeout=self.timeout_s) as client:
            uploaded = await client.post(
                LLAMA_UPLOAD_URL,
                headers=headers,
                files={"file": (filename, data, mime_type or "application/pdf")},
            )
            uploaded.raise_for_status()
            job = uploaded.json()
            job_id = job.get("id")
            if not job_id:
                raise ValueError("LlamaParse upload response missing id")
            markdown_url = (
                f"https://api.cloud.llamaindex.ai/api/parsing/job/{job_id}/result/markdown"
            )
            status_url = f"https://api.cloud.llamaindex.ai/api/parsing/job/{job_id}"
            for _ in range(MAX_POLLS):
                status = await client.get(status_url, headers=headers)
                status.raise_for_status()
                state = str(status.json().get("status") or "").lower()
                if state in {"success", "completed"}:
                    result = await client.get(markdown_url, headers=headers)
                    result.raise_for_status()
                    payload = result.json()
                    return str(payload.get("markdown") or payload.get("text") or "")
                if state in {"error", "failed"}:
                    raise ValueError(f"LlamaParse job {job_id} failed")
                await asyncio.sleep(POLL_INTERVAL_S)
        raise TimeoutError("LlamaParse job did not complete in time")
