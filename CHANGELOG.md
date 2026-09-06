# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/);
versioning follows [Semantic Versioning](https://semver.org/).

## [0.1.0] — initial skeleton

### Added
- Core abstractions: `ResolvableItem`, `RetrievalResult`/`RetrievalError`/`Candidate`
- `Router` with both tracks: fast-path fetch (hash-skip, retry/backoff,
  config-driven escalation, PDF-to-Parser hand-off) and discovery
  (trust filtering, duplicate discarding, `require_review`-gated merge rules)
- `wyndpy.factory.build_router()` / `build_scheduler()` wiring a `Policy`
  into running objects, including entry-point based third-party adapter discovery
- Working `HttpxFetcher` (SSRF guards, connection pooling, empty-shell
  detection); structurally-correct stubs for `FirecrawlFetcher`,
  `ExaSearcher`, `LlamaParseParser` (real API calls not yet wired in)
- Policy loader with clear, consistent `PolicyError`s (not raw `KeyError`/
  `YAMLError`/`FileNotFoundError`)
- Top-level package API (`from wyndpy import Router, load_policy, ...`)
- Logging throughout the router and httpx adapter; never logs credentials
- `py.typed` marker, `ruff` + `mypy` configured and clean
- `llm_eval` pytest marker + `--run-llm-eval` gating for quality-drift evals
- MIT license

### Known limitations (see README for detail)
- No real Firecrawl/Exa/LlamaParse API calls yet
- No Postgres registry implementation (stub only)
- Cost-cap/rate-limit config is parsed but not enforced
- No structured/persistent resolution audit log (stdlib logging only)
- No real MCP server transport (tool registry exists, transport doesn't)
- Hash-skip assumes byte-stable content — breaks on pages with per-request
  dynamic tokens (e.g. CSRF nonces); confirmed via live testing against
  `github.com` vs. a static `raw.githubusercontent.com` resource
