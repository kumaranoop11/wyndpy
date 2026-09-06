# Wyndpy

Generic, pluggable content-retrieval library. Given an item with no known
source (or a partially known one), Wyndpy finds it, fetches it, and parses
it into clean structured content — using swappable adapters behind three
roles (`Fetcher`, `Searcher`, `Parser`), never hardcoded tool names.

See `wyndpy_design_spec.md` (or your copy of it) for the full design
rationale.

## Status

Fully implemented and tested against the design spec:

- Core abstractions (`ResolvableItem`, `RetrievalResult`/`RetrievalError`/`Candidate`)
- **`Router`** implementing both tracks end to end:
  - Track A fast path: hash-skip, retry-with-backoff on transient errors,
    **config-driven escalation** (reads `escalation_rules` from policy — not
    a hardcoded list), PDF content-type routing to a Parser adapter,
    `fetch_exhausted` terminal state, single-flight locking per item
  - Track B discovery: trust filtering, duplicate-discovery discarding, and
    the full **merge-rule** behavior (new item -> promoted, gated by
    `require_review`; existing item -> alternate staged in
    `candidate_sources`, never auto-replaced)
  - `require_review` (default `True`) actually gates auto-fetch of a
    newly-promoted source — a real bug fix: it was previously parsed into
    config and never consulted, so a freshly-discovered source was
    auto-fetched regardless of this setting, contradicting "nothing
    auto-promotes." Now `require_review=True` leaves a new discovery at
    `PENDING_REVIEW` with no fetch; `require_review=False` is an explicit
    opt-in for pipelines that want full automation.
  - Legacy/standalone mode (no `escalation_rules` passed) still works for
    adapters used directly with no policy file
- **`wyndpy.factory.build_router(policy, credentials)`** and
  **`wyndpy.factory.build_scheduler(policy)`** — the pieces that actually
  wire a `Policy` into running objects: instantiates adapters via entry
  points, builds the trust strategy and registry backend, passes
  `escalation_rules` through, and returns a `CronScheduler`/`EventScheduler`
  per `scheduling_backend`. Verified against a real live fetch
  (`github.com`) end to end: policy.yaml -> factory -> router -> httpx ->
  hashed, resolved item. 12 dedicated tests in `tests/test_factory.py`.
- Working default adapter: `HttpxFetcher` (SSRF guards, timeouts,
  empty-shell detection, SHA-256 hashing, raw-bytes passthrough for PDFs)
- Adapter *stubs* (correct shape, `NotImplementedError` on the actual API
  call) for `FirecrawlFetcher`, `ExaSearcher`, `LlamaParseParser` — wire up
  the real API calls before using these three live
- `AllowlistTrust`, `MemoryRegistry`, `PostgresRegistry` (stub),
  `CronScheduler`/`EventScheduler`
- Policy loader + `schema_version` validation
- Entry-point based adapter discovery — third-party adapters register
  under `wyndpy.fetch` / `wyndpy.search` / `wyndpy.parse`
- Tool-call schema generator + MCP tool registry, both built on one shared
  schema source (an adapter method's signature + docstring)
- `FakeFetcher`/`FakeSearcher`/`FakeParser` for adapter-free unit testing
- **`llm_eval` pytest marker** + `--run-llm-eval` flag: quality-drift evals
  are collected but skipped by default, matching the FabricIQ pattern this
  library originated from (`tests/eval/`)
- 27 passing tests covering every path above (`tests/test_router_smoke.py`,
  `tests/test_router_gaps_closed.py`, `tests/test_factory.py`,
  `tests/test_httpx_adapter.py`)

## Known limitations (honest, not silently missing)

- **Firecrawl / Exa / LlamaParse have no real API calls wired in** — they're
  structurally correct stubs (`NotImplementedError`) so the router logic
  around them is fully tested, but nothing will actually call these APIs
  until you fill them in.
- **Postgres registry is a stub** — bring your own DB access layer.
- **Cost-cap / rate-limit *enforcement*** — config fields exist and are
  parsed, but the router doesn't yet throttle or reject calls based on
  them (retry/backoff on a 429 is implemented; a hard cap is not).
- **No structured resolution log emitted yet** (spec §9) — the router has
  everything needed to build one (adapter name, outcome, error type per
  attempt) but doesn't write it anywhere yet.
- **No real MCP server transport** — `AdapterToolRegistry` exists and
  produces correct schemas/handlers; wiring it into an actual MCP SDK's
  server loop is left to the consuming project.
- **The empty-shell heuristic is intentionally crude** (visible-text length
  threshold) — verified it correctly flags a real JS-shell-like short page
  as a false positive on very small legitimate pages (e.g. `example.com`'s
  placeholder page). Tune `EMPTY_SHELL_TEXT_THRESHOLD` or replace the
  heuristic for production use.
- **`asyncio.Lock`-based single-flight is in-process only** — fine for a
  single worker; a distributed deployment needs a distributed lock instead.
- **`build_scheduler()` only builds the scheduler object** — registering
  the actual Track A/B jobs against it (what "every cycle" iterates over,
  etc.) is left to the consuming project, since those callables are
  inherently project-specific.
- **Hash-skip assumes byte-stable content — found to break on pages with
  per-request dynamic tokens.** Verified via a real end-to-end run:
  fetching `github.com/pypa/pip` twice produced two *different* SHA-256
  hashes for "unchanged" content, because GitHub injects a fresh CSRF
  token into every page load. Confirmed this is specific to dynamic-token
  pages, not a hashing bug, by fetching a genuinely static resource
  (`raw.githubusercontent.com`) twice and getting identical hashes both
  times. This matches the library's original use case (static vendor
  datasheets) but is a real limitation on dynamically-rendered pages —
  a production deployment targeting such pages would need a
  content-normalization step (stripping known volatile fields) before
  hashing, which isn't implemented here.

## Install

```bash
pip install -e .                              # core only (httpx fetch works out of the box)
pip install -e ".[firecrawl,exa,llamaparse]"  # add adapters as needed
pip install -e ".[dev]"                       # pytest + pytest-asyncio
```

## Quick start — direct call, no policy file

```python
import asyncio
from wyndpy.fetch.httpx_adapter import HttpxFetcher

async def main():
    fetcher = HttpxFetcher(allowlist_domains=["github.com"])
    result = await fetcher.fetch("https://github.com/pypa/pip")
    print(result)

asyncio.run(main())
```

## Quick start — top-level API (the ergonomic path)

```python
import asyncio
from wyndpy import load_policy, build_router, ResolvableItem

# examples/policy.example.yaml lists firecrawl/exa/llamaparse in `roles` —
# those need credentials (see note below) or build_router() raises a
# PolicyError naming exactly which adapter is missing them. A policy with
# only `roles: {fetch: [httpx]}` needs no credentials at all.
policy = load_policy("examples/policy.example.yaml")
router = build_router(policy, credentials={
    "httpx": {"allowlist_domains": ["your-vendor.com"]},
    "firecrawl": {"api_key": "..."},
    "exa": {"api_key": "..."},
    "llamaparse": {"api_key": "..."},
})

item = ResolvableItem(id="sku-1", query_hint="...", current_sources=["https://your-vendor.com/spec"])
result = asyncio.run(router.resolve_known_source(item))
```

> **Every adapter listed in `policy.roles` gets constructed immediately**
> by `build_router()`, so it needs its credentials up front even if you
> never end up calling it (e.g. `firecrawl` only fires on an httpx
> empty-shell). Leave an adapter out of `roles` entirely if you don't have
> credentials for it yet — `build_router()` will tell you exactly which
> adapter and role are missing if you forget one.

Everything is still importable from its actual submodule too
(`wyndpy.core.router.Router`, `wyndpy.fetch.httpx_adapter.HttpxFetcher`,
etc.) — the top-level surface (`wyndpy.Router`, `wyndpy.load_policy`,
`wyndpy.__version__`, ...) is a convenience, not the only way in.

## Quick start — policy-driven router (module path, if you prefer explicit imports)

```python
from wyndpy.policy import load_policy
from wyndpy.factory import build_router
from wyndpy.core.item import ResolvableItem
import asyncio

policy = load_policy("examples/policy.example.yaml")
router = build_router(policy, credentials={
    "httpx": {"allowlist_domains": ["your-vendor.com"]},
    # "firecrawl": {"api_key": "..."},  # once wired up
})

item = ResolvableItem(id="sku-1", query_hint="...", current_sources=["https://your-vendor.com/spec"])
result = asyncio.run(router.resolve_known_source(item))
```

## Quick start — router with fakes (no network)

See `tests/test_router_smoke.py` and `tests/test_router_gaps_closed.py`
for full examples of every path: fast path, escalation (legacy and
config-driven), retry/backoff, PDF hand-off to a Parser, and all three
discovery merge rules.

## Development

```bash
pip install -e ".[dev]"
python -m ruff check wyndpy/ tests/     # lint
python -m mypy wyndpy/                  # type-check (clean on 36 source files)
python -m pytest tests/ -v              # test
```

Best-practices additions beyond the core logic:
- **`py.typed` marker (PEP 561)** — type checkers in a *consuming* project
  will actually trust this package's type hints, not silently ignore them
- **Logging** (`logging.getLogger("wyndpy.router")`, `"wyndpy.fetch.httpx"`)
  at every decision point — fetch attempts, hash-skip, escalation
  (both legacy and config-driven), retries, discovery merge outcomes,
  terminal states. Never logs credentials — verified by grep, not just claimed.
- **Connection pooling**: `HttpxFetcher` reuses one `httpx.AsyncClient`
  across calls instead of paying a fresh TCP/TLS handshake per fetch.
  Supports `async with HttpxFetcher(...) as f:` for clean shutdown, or
  inject a shared client via the `client=` constructor arg.
- **MIT `LICENSE`** — a library meant for reuse across projects needs one
- **Explicit package discovery** (`[tool.setuptools.packages.find]`) instead
  of relying on implicit autodiscovery
- **`ruff` + `mypy` configured and passing clean** (`mypy`: 0 errors across
  36 source files; `ruff`: 0 findings, including the `StrEnum` modernization
  for `ItemStatus`/`ErrorType` since `requires-python >= 3.11` already
  supports it)
- **Top-level import ergonomics**: `from wyndpy import Router, load_policy,
  build_router, ResolvableItem, ...` instead of forcing every caller to
  know internal module paths. `wyndpy.__version__` reads from installed
  package metadata (no hardcoded version to drift out of sync with
  `pyproject.toml`).
- **Consistent, catchable errors from the policy loader**: malformed YAML,
  a missing file, and an incomplete `escalation_rules` entry all raise a
  clear `PolicyError` with a specific message — not a raw `KeyError`,
  `ScannerError`, or `FileNotFoundError` leaking through.
- **Packaging verified against a real built wheel, not just an editable
  install**: ran `python -m build`, confirmed `py.typed` and all three
  entry-point groups actually land in the wheel's `RECORD`, then installed
  that wheel into a completely fresh venv and ran a full policy -> router
  -> live-fetch flow through the top-level `wyndpy` API with no dev
  environment involved.
- **Adapter-construction failures are catchable, specific errors**: a
  missing required constructor arg (e.g. no `api_key` for `firecrawl`)
  used to surface as a raw `TypeError` from deep inside the adapter's
  `__init__`. Found by actually running the README's own quick-start
  verbatim — it crashed. Now raises `PolicyError` naming the adapter, the
  role, and exactly which `credentials={...}` key to add.
- **`.github/workflows/ci.yml`**: lints (`ruff`), type-checks (`mypy`),
  and tests on Python 3.11 + 3.12, then separately builds a real wheel,
  installs *only* that wheel into a fresh venv, and smoke-tests it. That
  second job caught a real bug while being written: the smoke-test step
  originally ran with cwd = the repo root, and `python -c "import
  wyndpy"` puts cwd on `sys.path` *before* site-packages — so it was
  silently shadow-importing the source tree instead of the installed
  wheel, defeating the entire purpose of the check. Confirmed by
  reproducing the exact same command from two different working
  directories and getting two different `wyndpy.__file__` results. Fixed
  by pinning `working-directory: /tmp` on that step.
- **`pip-audit` run against runtime dependencies** (`httpx`, `pyyaml`) —
  no known vulnerabilities as of this writing.
- **`CHANGELOG.md`** added (Keep a Changelog format).


