# ruff: noqa: F403, F405
from __future__ import annotations

from tests._compress_audit_testkit import *


def test_trace_arg_summary_redacts_write_and_exec() -> None:
    from bao.agent.shared import summarize_tool_args_for_trace

    write_preview = summarize_tool_args_for_trace(
        "write_file",
        {"path": "src/app.py", "content": "secret"},
    )
    exec_preview = summarize_tool_args_for_trace("exec", {"command": "echo secret"})

    assert write_preview == "src/app.py"
    assert exec_preview.startswith("<redacted:")


def test_trace_entry_sanitizes_newlines() -> None:
    from bao.agent.shared import ToolTraceEntryRequest, build_tool_trace_entry

    entry = build_tool_trace_entry(
        ToolTraceEntryRequest(
            trace_idx=1,
            tool_name="exec",
            args_preview="line1\nline2",
            has_error=False,
            result="ok\nnext",
        )
    )
    assert "\n" not in entry
    assert "line1 line2" in entry


def test_push_failed_direction_keeps_recent_window() -> None:
    from bao.agent.shared import push_failed_direction

    failed: list[str] = []
    for i in range(25):
        push_failed_direction(failed, f"f{i}")

    assert len(failed) == 20
    assert failed[0] == "f5"
    assert failed[-1] == "f24"


def test_push_failed_direction_deduplicates_adjacent_entries() -> None:
    from bao.agent.shared import push_failed_direction

    failed: list[str] = []
    push_failed_direction(failed, "exec(a)")
    push_failed_direction(failed, "exec(a)")
    push_failed_direction(failed, "exec(b)")
    assert failed == ["exec(a)", "exec(b)"]
