# Adapter output-quality evals

Separate from `tests/test_router_*.py` (fast, network-free, run on every
`pytest`), this directory holds evals for adapters whose *output quality*
can drift — search relevance being the main case, since it depends on the
upstream API's ranking, not just its uptime.

## Running

```bash
pytest tests/eval/ --run-llm-eval -v
```

Without `--run-llm-eval`, these tests are collected but skipped — so a
normal `pytest` run never depends on network access or API keys.

## Adding a real eval

1. Record a cassette: capture a real adapter response for a known query
   against a known fixture (don't record against production data).
2. Save it under `cassettes/`.
3. Write an expected-fields golden (what a *correct* response should
   contain) alongside it.
4. Assert precision/recall/faithfulness against that golden, not against
   the raw cassette — the cassette is the input, the golden is the answer key.
5. Re-run this eval whenever the adapter's prompt, model, or API version
   changes — not on every commit.
