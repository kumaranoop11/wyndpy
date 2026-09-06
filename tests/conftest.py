"""Skips `llm_eval`-marked tests unless explicitly requested.

Mirrors the pattern of separating fast, network-free unit tests from
slower quality-drift evals: `pytest` alone never runs live-adapter evals;
`pytest --run-llm-eval` does.
"""
from __future__ import annotations

import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--run-llm-eval",
        action="store_true",
        default=False,
        help="Run tests marked llm_eval (adapter output-quality evals).",
    )


def pytest_collection_modifyitems(config, items):
    if config.getoption("--run-llm-eval"):
        return
    skip_eval = pytest.mark.skip(reason="need --run-llm-eval option to run")
    for item in items:
        if "llm_eval" in item.keywords:
            item.add_marker(skip_eval)
