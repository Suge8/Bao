from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from bao.agent.loop import AgentLoop
from bao.bus.queue import MessageBus
from bao.config.schema import Config, ToolExposureConfig, ToolsConfig
from bao.providers.base import LLMProvider, LLMResponse


class EvalDummyProvider(LLMProvider):
    def __init__(self) -> None:
        super().__init__(api_key=None, api_base=None)

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        on_progress=None,
        **kwargs: Any,
    ) -> LLMResponse:
        del messages, tools, model, max_tokens, temperature, on_progress, kwargs
        return LLMResponse(content="ok", finish_reason="stop")

    def get_default_model(self) -> str:
        return "dummy/model"


def load_tool_exposure_cases(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    cases = payload.get("cases", [])
    return list(cases) if isinstance(cases, list) else []


def evaluate_tool_exposure_cases(
    *,
    workspace: Path,
    cases: list[dict[str, Any]],
    default_bundles: list[str] | None = None,
    mode_override: str | None = None,
    bundles_override: list[str] | None = None,
) -> dict[str, Any]:
    os.environ.setdefault("BRAVE_API_KEY", "tool-exposure-eval")
    selected_default_bundles = list(default_bundles or ["core", "web", "desktop", "code"])
    run_id = datetime.now().isoformat(timespec="seconds")
    case_results: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    visible_tool_total = 0
    prompt_chars_total = 0

    for case in cases:
        mode = str(mode_override or case.get("expected_mode") or "auto")
        bundles = list(bundles_override or case.get("run_with_bundles") or selected_default_bundles)
        cfg = Config(tools=ToolsConfig(tool_exposure=ToolExposureConfig(mode=mode, bundles=bundles)))
        loop = AgentLoop(
            bus=MessageBus(),
            provider=EvalDummyProvider(),
            workspace=workspace,
            config=cfg,
        )
        snapshot = loop._build_tool_exposure_snapshot(
            initial_messages=[
                {"role": "system", "content": "tool exposure eval"},
                {"role": "user", "content": str(case.get("input") or "")},
            ],
            tool_signal_text=None,
            exposure_level=0,
            force_final_response=False,
        )
        visible_tools = (
            set(loop.tools.tool_names) if snapshot.full_exposure else set(snapshot.ordered_tool_names)
        )
        available_tools = set(loop.tools.tool_names)
        prompt_chars = sum(len(line) for line in snapshot.available_tool_lines)
        visible_tool_total += len(visible_tools)
        prompt_chars_total += prompt_chars

        reasons: list[str] = []
        if mode != "off":
            expected_bundles = set(case.get("expected_auto_bundles") or [])
            actual_bundles = set(snapshot.selected_bundles)
            if actual_bundles != expected_bundles:
                reasons.append(
                    f"selected_bundles mismatch: expected={sorted(expected_bundles)} actual={sorted(actual_bundles)}"
                )

        for tool_name in case.get("expect_tools_present", []):
            if tool_name in available_tools and tool_name not in visible_tools:
                reasons.append(f"missing tool: {tool_name}")
        for tool_name in case.get("expect_tools_absent", []):
            if tool_name in available_tools and tool_name in visible_tools:
                reasons.append(f"unexpected tool: {tool_name}")

        passed = not reasons
        case_result = {
            "case_id": str(case.get("id") or ""),
            "passed": passed,
            "mode": mode,
            "bundles": bundles,
            "selected_bundles": list(snapshot.selected_bundles),
            "visible_tool_count": len(visible_tools),
            "prompt_chars": prompt_chars,
            "reasons": reasons,
        }
        case_results.append(case_result)
        if not passed:
            failures.append(
                {
                    "case_id": case_result["case_id"],
                    "reason": "; ".join(reasons),
                }
            )

    total_cases = len(case_results)
    passed_cases = sum(1 for item in case_results if item["passed"])
    failed_cases = total_cases - passed_cases
    return {
        "run_id": run_id,
        "mode": mode_override or "mixed",
        "bundles": list(bundles_override or selected_default_bundles),
        "summary": {
            "total_cases": total_cases,
            "passed": passed_cases,
            "failed": failed_cases,
            "pass_rate": (passed_cases / total_cases) if total_cases else 0.0,
        },
        "metrics": {
            "visible_tool_count_avg": (visible_tool_total / total_cases) if total_cases else 0.0,
            "avg_prompt_chars": (prompt_chars_total / total_cases) if total_cases else 0.0,
        },
        "failures": failures,
        "cases": case_results,
    }


def write_tool_exposure_eval_artifact(output_dir: Path, payload: dict[str, Any]) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = output_dir / f"tool_exposure_eval_{stamp}.json"
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return target
