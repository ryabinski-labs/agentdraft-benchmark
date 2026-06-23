"""Offline smoke tests — import the harness and exercise its pure helpers.

No network and no AgentDraft instance required; these guard the CLI surface
and the key/agent plumbing so a broken refactor fails CI.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

RUN_PY = Path(__file__).resolve().parent.parent / "run.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("benchmark_run", RUN_PY)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    # Register before exec so @dataclass can resolve the module (Python 3.12+).
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


run = _load_module()


def test_agents_from_keys_assigns_descending_priority():
    agents = run.agents_from_keys(["k1", "k2", "k3"])
    assert [rank for (_, _, rank) in agents] == [1, 2, 3]
    assert [key for (_, key, _) in agents] == ["k1", "k2", "k3"]
    # First named agent is the highest-priority NAMES entry.
    assert agents[0][0] == run.NAMES[0]


def test_agents_from_keys_strips_whitespace():
    (_, key, _) = run.agents_from_keys([" k1 "])[0]
    assert key == "k1"


def test_agents_from_keys_beyond_named_list_falls_back():
    keys = [f"k{i}" for i in range(len(run.NAMES) + 2)]
    agents = run.agents_from_keys(keys)
    assert agents[-1][0] == f"agent-{len(keys)}"


def test_aggregate_empty_is_safe():
    agg = run.aggregate([])
    assert agg["rounds"] == 0
    assert agg["conflict_resolution_accuracy"] == 0.0


def test_aggregate_counts_one_winner_round():
    R = run.Result
    rounds = [[
        R("a", 1, 5.0, "201", "COMMITTED", "bkg_1", None, None),
        R("b", 2, 6.0, "409", "outranked", None, "a", 1),
    ]]
    agg = run.aggregate(rounds)
    assert agg["committed"] == 1
    assert agg["rejected_409"] == 1
    assert agg["rounds_with_exactly_one_winner"] == 1
    assert agg["rounds_with_double_commit"] == 0
    assert agg["conflict_resolution_accuracy"] == 1.0
    assert agg["rank1_win_rate"] == 1.0


def test_aggregate_flags_double_commit():
    R = run.Result
    rounds = [[
        R("a", 1, 5.0, "201", "COMMITTED", "bkg_1", None, None),
        R("b", 2, 6.0, "201", "COMMITTED", "bkg_2", None, None),
    ]]
    agg = run.aggregate(rounds)
    assert agg["rounds_with_double_commit"] == 1
    assert agg["rounds_with_exactly_one_winner"] == 0


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
