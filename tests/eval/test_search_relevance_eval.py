"""Example adapter-quality eval, run only with `pytest --run-llm-eval`.

Real evals would replay a recorded cassette (a saved request/response pair
for a given adapter + fixture page) and score precision/recall/faithfulness
against an expected-fields golden — see design spec §9, Testing. This file
is a template showing the shape, not a real eval yet (no cassettes are
recorded — that requires an actual adapter + API key to record against).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

CASSETTE_DIR = Path(__file__).parent / "cassettes"


@pytest.mark.llm_eval
def test_example_searcher_relevance_against_cassette():
    """Template: replace with a real cassette once ExaSearcher is wired up.

    A real version would:
      1. load a recorded cassette (request + response JSON) instead of
         hitting the live Exa API
      2. run it through ExaSearcher's response-normalization logic only
         (not the network call)
      3. compare returned Candidates against an expected-fields golden
      4. assert precision/recall/faithfulness above a threshold
    """
    cassette_path = CASSETTE_DIR / "exa_example.json"
    if not cassette_path.exists():
        pytest.skip(
            "No recorded cassette yet — record one against a real Exa "
            "response before this eval is meaningful."
        )
        return

    cassette = json.loads(cassette_path.read_text())
    assert "candidates" in cassette  # placeholder assertion
