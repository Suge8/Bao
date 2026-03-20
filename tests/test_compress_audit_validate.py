# ruff: noqa: F403, F405
from __future__ import annotations

from tests._compress_audit_testkit import *


def test_validate_state_fills_missing_conclusions() -> None:
    from bao.agent.shared import _validate_state

    result = {"evidence": "some evidence", "unexplored": "try X"}
    trace = ["T1 read(f) → ok", "T2 search(q) → ok"]
    validated = _validate_state(result, trace, [])
    assert "conclusions" in validated
    assert "2 steps" in validated["conclusions"]


def test_validate_state_fills_missing_evidence() -> None:
    from bao.agent.shared import _validate_state

    result = {"conclusions": "found it", "unexplored": "try Y"}
    trace = ["T1 read(f) → ok", "T2 exec(cmd) → ERROR", "T3 search(q) → ok"]
    validated = _validate_state(result, trace, ["exec(cmd)"])
    assert "evidence" in validated
    assert "read" in validated["evidence"] or "search" in validated["evidence"]


def test_validate_state_fills_unexplored_from_failures() -> None:
    from bao.agent.shared import _validate_state

    result = {"conclusions": "partial", "evidence": "T1"}
    validated = _validate_state(result, ["T1 a → ok"], ["b(x)", "c(y)"])
    assert "unexplored" in validated
    assert "Retry" in validated["unexplored"]


def test_validate_state_fills_unexplored_without_failures() -> None:
    from bao.agent.shared import _validate_state

    result = {"conclusions": "partial", "evidence": "T1"}
    validated = _validate_state(result, ["T1 a → ok"], [])
    assert "unexplored" in validated
    assert "verify remaining requirements" in validated["unexplored"]
