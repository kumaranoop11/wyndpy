# Wyndpy — Design Spec v0.1

A generic, pluggable content-retrieval library. Given an item with no known
source (or a partially known one), Wyndpy finds it, fetches it, and parses it
into clean structured content — using swappable adapters, never hardcoded
tool names.

Originated from FabricIQ's catalog ingestion pipeline (Firecrawl / Exa /
LlamaParse escalation ladder), generalized so any project can reuse it with
its own sources, trust rules, and tool choices.

---

## 1. Design principles

1. **Roles, not tool names.** Core code only knows `Fetcher`, `Searcher`,
   `Parser` — three protocols. It has zero awareness that Firecrawl, Exa, or
   LlamaParse exist. Today's adapters are swappable for any future tool that
   satisfies the same protocol.
2. **Config drives behavior, not code.** Which adapters are enabled, escalation
   rules, trust strategy, discovery cadence, cost caps — all in one policy
   file per project. Two unrelated projects share the same library, different
   config.
3. **Everything usable standalone.** Any adapter can be imported and called
   directly, with zero dependency on the router, registry, or policy file.
   Any adapter can also be omitted from config with zero code breakage
   elsewhere.
4. **One implementation, three call surfaces.** Direct Python call, native
   tool-call schema, MCP server — all wrap the same adapter method. Schema/
   description generated from one definition, never hand-duplicated.
5. **Nothing auto-promotes.** Discovered sources pass through a review gate
   before being trusted — the same discipline a project would apply to any
   extracted value, applied here one level up, to sources themselves.
6. **Async-first.** All protocol methods (`fetch`, `search`, `parse`) are
   defined as `async`. A sync wrapper is provided for direct-call convenience
   (`surface/direct.py`), but the core interfaces and router are async so
   discovery cycles over many items and agentic callers aren't blocked on
   sequential I/O.

---

## 2. Core abstractions

### `ResolvableItem`
Domain-blind representation of anything the library is trying to source
content for.

```
ResolvableItem:
  id: str
  query_hint: str                # used by Searcher role
  current_source(s): list[str]?  # known URLs, if any
  metadata: dict                 # project-specific, opaque to core
```

### Roles (protocols)

| Role | Method | Purpose |
|---|---|---|
| `FetcherProtocol` | `async fetch(url) -> RetrievalResult \| RetrievalError` | Get content from a known URL |
| `SearcherProtocol` | `async search(query, n=10) -> list[Candidate]` | Find candidate URLs from a query |
| `ParserProtocol` | `async parse(bytes, mime_type) -> RetrievalResult \| RetrievalError` | Convert a document/file into structured content |

### Shared result types

```
RetrievalResult: { content, content_type, source_url, content_hash,
                    retrieved_at, provider_used }
RetrievalError:  { error_type, message, provider_used }
                  # typed: EmptyShellError, UnsupportedFormatError, NotFoundError
Candidate:       { url, relevance_score, snippet }
```

`content_hash` is SHA-256 of the raw response body, computed identically by
every Fetcher/Parser adapter. This guarantees hash-skip works across
adapters and re-fetches — two adapters hashing differently would silently
break Track A's skip logic.

Adapters normalize each tool's native response into these shapes. Core code
never sees a tool-specific field.

---

## 3. Two tracks

### Track A — Fast path (known sources, runs every cycle)
```
1. url known → Fetcher role, ordered adapter fallback (e.g. httpx → Firecrawl)
2. hash matches last run → skip, no downstream call
3. escalate only on a typed error from the ordered fallback list
4. content_type == pdf → Parser role instead of continuing the Fetcher chain
5. every adapter in the chain fails → item marked `fetch_exhausted`
   (distinct from `unresolved`: the source was known but unreachable,
   a different debugging story than "never found")
```

### Track B — Discovery (decoupled cadence)
```
- New item, no known source → Searcher role every cycle (nothing to skip)
- Existing item, source already known → Searcher role on a separate,
  slower cadence (config: fixed schedule or event-triggered, e.g. on
  fetch failure or staleness threshold)
- Candidate found, item had no prior source → promoted + marked
  `pending_review`. Re-enters Track A's fetch chain ONLY if
  `require_review=False` (an explicit opt-in for fully-automated
  pipelines). Default `require_review=True` leaves it staged, unfetched,
  until a human/process approves it — this is what "nothing auto-promotes"
  (principle 5) actually means in practice, not just for the value, but
  for the fetch itself.
- Candidate found, item already had a source → staged as
  `candidate_source`, never auto-fetched either way
- No usable candidate found → item stays unresolved (no auto fallback
  to manual entry)
```

### Merge rules — discovered source vs. trusted registry

| Discovery result | Action |
|---|---|
| New URL, item had no registry entry | Add as `pending_review` |
| New URL, item already has a registered source | Stage as `candidate_source`, never auto-replace — surfaced in review |
| Duplicate of a previously-seen discovery | Discard silently |

---

## 4. Configuration (policy file, per project)

```yaml
schema_version: 1                # required; library validates/migrates against this

roles:
  fetch: [httpx, firecrawl]      # ordered fallback within the role
  search: [exa]                  # swappable later, e.g. tavily
  parse: [llamaparse]

search:
  candidate_count: 10            # configurable, default 10

escalation_rules:
  - trigger: empty_shell
    from: httpx
    to: firecrawl
  - trigger: content_type=pdf
    from: httpx
    to: llamaparse

discovery:
  new_items: every_cycle
  existing_items:
    cadence: monthly            # or: event_triggered
    trigger_on: [fetch_failure, stale_after_days:90]

trust:
  strategy: allowlist            # default; overridable — reputation | custom
  allow: ["*.example.com"]
  require_review: true

unresolved_handling: leave_unresolved   # no auto manual-entry fallback

registry_backend: postgres        # pluggable: postgres | sqlite | memory
scheduling_backend: cron          # pluggable: cron | background_task | event

cost_caps:                        # optional per adapter; omit to leave uncapped
  exa: 50/day
  firecrawl: 200/day
  llamaparse: 100/day

rate_limits:                      # separate from cost_caps — a 429 is a
  exa: 5/minute                   # backoff-and-retry case, not a budget
  firecrawl: 10/minute             # breach; distinct handling in the router
```

Swapping a tool (e.g. Exa → a future alternative) is a one-line config change,
provided the new adapter satisfies `SearcherProtocol`. No router, discovery,
or trust code changes.

---

## 5. Adapter contract

- Each adapter implements exactly one role's protocol.
- Adapters normalize tool-native responses into the shared result types.
- No adapter imports another adapter — all escalation logic lives in the
  router only.
- Optional installs stay optional at *runtime*: importing an adapter whose
  extra isn't installed only fails when something actually tries to use it,
  never at package load.
- Auth/config is per-adapter (constructor args), so standalone use never
  requires a full project policy file to exist.

---

## 6. Three call surfaces, one implementation

```
                    Adapter.method()   ← logic lives once
                       ▲    ▲    ▲
           ┌───────────┘    │    └───────────┐
      Direct call     Tool-call schema     MCP server
   (plain import)   (agent SDK function)  (any MCP client)
```

- **Direct** — `FirecrawlAdapter().fetch(url)`, plain function call.
- **Tool-call** — same method, wrapped with a generated JSON schema for
  LLM native tool-calling.
- **MCP** — same method again, exposed as an MCP tool over a server, callable
  by any MCP client regardless of language/codebase.

Schema/description for the latter two is generated from one shared
definition (method signature + docstring) on the adapter — never a
hand-written parallel copy.

---

## 7. Package layout

```
wyndpy/
  core/
    item.py             # ResolvableItem
    router.py           # role-agnostic escalation logic (fast path + discovery)
    results.py          # RetrievalResult, RetrievalError, Candidate
    escalation.py        # EscalationRule — shared by policy.py and router.py
    discovery.py          # entry-point based adapter lookup (roles -> classes)
  fetch/
    protocol.py          # FetcherProtocol
    httpx_adapter.py
    firecrawl_adapter.py
  search/
    protocol.py          # SearcherProtocol
    exa_adapter.py
  parse/
    protocol.py          # ParserProtocol
    llamaparse_adapter.py
  trust/
    protocol.py          # TrustStrategy
    allowlist.py         # default
  registry/
    protocol.py
    postgres_adapter.py
    memory_adapter.py
  scheduling/
    protocol.py
    cron_adapter.py
    event_adapter.py
  surface/
    direct.py            # re-exports for plain import usage
    tool_schema.py        # generates tool-call schemas from adapters
    mcp_server.py          # exposes adapters as MCP tools
  testing/
    fake_adapters.py        # FakeFetcher/FakeSearcher/FakeParser — no-network unit testing
  policy.py                # loads + validates project YAML
  factory.py                # builds a Router/Scheduler FROM a loaded Policy —
                             # the piece that makes "config drives behavior" real
```

Optional installs: `pip install wyndpy[firecrawl]`, `wyndpy[exa]`,
`wyndpy[llamaparse]`, or `wyndpy[all]`.

### Supporting protocols (minimum shape)

| Protocol | Method | Purpose |
|---|---|---|
| `TrustStrategy` | `is_trusted(candidate: Candidate) -> bool` | Decide if a discovered source may proceed past `pending_review` |
| `RegistryProtocol` | `get(item_id) -> ResolvableItem \| None`, `upsert(item)` | Persist known items/sources |
| `SchedulingProtocol` | `register(job, cadence_or_trigger)` | Wire a track to a cron/background-task/event backend |

---

## 8. Resolved decisions

| Question | Decision |
|---|---|
| Candidate count from Searcher role | Configurable, default `10` |
| Trust strategy default | `allowlist`, overridable per project |
| No usable discovery result | Item stays unresolved — no auto manual-entry fallback |
| Module grouping | By verb/role (`fetch/`, `search/`, `parse/`, etc.), not by tool name |
| Package name | **Wyndpy** |

---

## 9. Reliability, observability, testing & extensibility

Additions from a best-practices review — generic to any adapter-based
retrieval library, not FabricIQ-specific.

### Reliability
- **SSRF protection is a Fetcher-role requirement, not a per-project add-on.**
  Every Fetcher adapter refuses IP literals, `file://`, `localhost`/private
  ranges, and redirects that land outside the allowlisted domain. This
  matters most once Track B feeds in Searcher-discovered URLs — those are
  untrusted input, unlike a hand-registered source.
- **Timeout + max response size are required constructor fields on every
  adapter**, not just a default-adapter convention.
- **Retry policy is defined per-role, not per-adapter.** Transient network
  errors warrant backoff-and-retry; a typed `NotFoundError` does not —
  retrying it burns cost-cap budget for no gain.

### Observability
- **Structured resolution log per attempt**: adapter used, cost incurred,
  cache hit/miss, escalation path taken, outcome. This is what makes an
  unresolved item or an escalation-ladder tuning decision debuggable later,
  and is independent of whatever the consuming project does with the
  resolved content itself.
- **Cost tracking, not just a cost cap.** A cap prevents overspend; a
  running per-adapter cost log is what tells a project whether a given
  paid tool is earning its bill.

### Testing
- **`FakeAdapter` per role is a first-class citizen**: deterministic fixture
  responses so CI/unit tests never hit a live Fetcher/Searcher/Parser tool
  (the same "null provider" pattern common to any external-API-backed
  library).
- **Recorded-cassette eval marker** for adapters whose output quality can
  drift over time (search relevance especially) — separate from the
  fixture-based unit tests above, run on a schedule or on adapter/version
  change rather than every CI run.

### Extensibility
- **Adapter registration via entry points**, so a new adapter (a future
  Searcher alternative, for instance) can ship as its own installable
  package and register itself with Wyndpy, without forking or modifying
  core. This is what actually delivers on "later, other alternatives can
  be used" — a config change alone isn't enough if the adapter class isn't
  discoverable.

### Concurrency
- **Idempotency / single-flight per item.** If two callers (plausible under
  agentic use — multiple tool-calls in flight) request resolution for the
  same item concurrently, the router coalesces them into one in-flight
  attempt rather than double-spending Search/Fetch calls.

### Policy hygiene
- **`schema_version` field in the policy YAML**, so the library can detect
  and reject (or migrate) a config file written against an older version of
  Wyndpy, instead of silently misreading it.

---

## 10. Non-goals (v0.1)

- No built-in LLM extraction step (`extract_to_model()`-style logic stays
  outside this library — Wyndpy delivers clean, provenance-tagged content,
  not model calls).
- No opinion on what a project does with resolved content downstream
  (staging tables, review UI, etc. are project-specific).
- No bundled default MCP server config — the MCP surface is generated from
  adapters, but deployment/hosting is left to the consuming project.
