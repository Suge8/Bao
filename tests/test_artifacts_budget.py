# ruff: noqa: F403, F405
from __future__ import annotations

from bao.agent.artifacts_models import ToolOutputBudgetRequest
from tests._artifacts_testkit import *


def test_apply_tool_output_budget_offloads_file_backed_result(tmp_path: Path) -> None:
    from bao.agent.artifacts import apply_tool_output_budget

    store = _make_store(tmp_path, "session:budget")
    source = tmp_path / "large.txt"
    payload = "x" * 12000
    source.write_text(payload, encoding="utf-8")
    result = ToolTextResult(path=source, chars=len(payload), excerpt="preview", cleanup=True)

    processed, event = apply_tool_output_budget(
        ToolOutputBudgetRequest(
            store=store,
            tool_name="exec",
            tool_call_id="call_1",
            result=result,
            offload_chars=8000,
            preview_chars=3000,
            hard_chars=6000,
            ctx_mgmt="auto",
        )
    )

    assert event.offloaded is True
    assert event.offloaded_chars == len(payload)
    assert "offloaded" in processed
    assert not source.exists()


def test_apply_tool_output_budget_clips_file_backed_result_in_observe_mode(tmp_path: Path) -> None:
    from bao.agent.artifacts import apply_tool_output_budget

    source = tmp_path / "observe.txt"
    payload = "x" * 9000
    source.write_text(payload, encoding="utf-8")
    result = ToolTextResult(path=source, chars=len(payload), excerpt="preview", cleanup=True)

    processed, event = apply_tool_output_budget(
        ToolOutputBudgetRequest(
            store=None,
            tool_name="exec",
            tool_call_id="call_1",
            result=result,
            offload_chars=8000,
            preview_chars=3000,
            hard_chars=6000,
            ctx_mgmt="observe",
        )
    )

    assert event.offloaded is False
    assert event.hard_clipped is True
    assert "hard-truncated" in processed
    assert not source.exists()


def test_apply_tool_output_budget_offloads_persistent_file_without_removing_source(
    tmp_path: Path,
) -> None:
    from bao.agent.artifacts import apply_tool_output_budget

    store = _make_store(tmp_path, "session:persistent-budget")
    source = tmp_path / "persistent.txt"
    payload = "x" * 12000
    source.write_text(payload, encoding="utf-8")
    result = ToolTextResult(path=source, chars=len(payload), excerpt="preview", cleanup=False)

    processed, event = apply_tool_output_budget(
        ToolOutputBudgetRequest(
            store=store,
            tool_name="read_file",
            tool_call_id="call_1",
            result=result,
            offload_chars=8000,
            preview_chars=3000,
            hard_chars=6000,
            ctx_mgmt="auto",
        )
    )

    assert event.offloaded is True
    assert "offloaded" in processed
    assert source.exists()


def test_delete_session_removes_artifact_directory(tmp_path: Path) -> None:
    from bao.session.manager import SessionManager

    manager = SessionManager(tmp_path)
    key = "telegram:chat/1"
    store = _make_store(tmp_path, key)
    _ = store.write_text("tool_output", "stdout", "artifact")
    assert store.session_dir.exists()

    deleted = manager.delete_session(key)

    assert deleted is True
    assert not store.session_dir.exists()
