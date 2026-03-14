from __future__ import annotations

from pathlib import Path

from bao.agent.tool_exposure_eval import (
    evaluate_tool_exposure_cases,
    load_tool_exposure_cases,
    write_tool_exposure_eval_artifact,
)


def test_tool_exposure_eval_runner_writes_expected_schema(tmp_path: Path) -> None:
    cases_path = Path(__file__).resolve().parents[1] / "docs" / "tool-exposure-cases.json"
    payload = evaluate_tool_exposure_cases(
        workspace=tmp_path,
        cases=load_tool_exposure_cases(cases_path),
    )

    assert "run_id" in payload
    assert payload["summary"]["total_cases"] >= 1
    assert payload["summary"]["passed"] + payload["summary"]["failed"] == payload["summary"][
        "total_cases"
    ]
    assert "visible_tool_count_avg" in payload["metrics"]
    assert "avg_prompt_chars" in payload["metrics"]

    artifact = write_tool_exposure_eval_artifact(tmp_path / "artifacts", payload)
    assert artifact.exists()
    assert artifact.name.startswith("tool_exposure_eval_")
