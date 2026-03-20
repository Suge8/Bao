from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from bao.agent._tool_exposure_domains import DEFAULT_TOOL_EXPOSURE_DOMAINS
from bao.agent._tool_exposure_eval_models import (
    CaseEvaluationOutcome,
    CaseResultRequest,
    EvalSummaryRequest,
)
from bao.agent.loop import AgentLoop
from bao.bus.queue import MessageBus
from bao.config.schema import Config, ToolExposureConfig, ToolsConfig
from bao.providers.base import ChatRequest, LLMProvider, LLMResponse

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TOOL_EXPOSURE_CASES_PATH = PROJECT_ROOT / "docs" / "tool-exposure-cases.json"
_DEFAULT_TOOL_EXPOSURE_DOMAINS = list(DEFAULT_TOOL_EXPOSURE_DOMAINS)


class EvalDummyProvider(LLMProvider):
    def __init__(self) -> None:
        super().__init__(api_key=None, api_base=None)

    async def chat(self, request: ChatRequest) -> LLMResponse:
        del request
        return LLMResponse(content="ok", finish_reason="stop")

    def get_default_model(self) -> str:
        return "dummy/model"


def load_tool_exposure_cases(path: Path | None = None) -> list[dict[str, Any]]:
    cases_path = path or DEFAULT_TOOL_EXPOSURE_CASES_PATH
    payload = json.loads(cases_path.read_text(encoding="utf-8"))
    cases = payload.get("cases", [])
    return list(cases) if isinstance(cases, list) else []


def _resolve_case_mode(case: dict[str, Any], mode_override: str | None) -> str:
    return str(mode_override or case.get("expected_mode") or "auto")


def _resolve_case_domains(
    case: dict[str, Any],
    *,
    selected_default_domains: list[str],
    domains_override: list[str] | None,
) -> list[str]:
    return list(domains_override or case.get("run_with_domains") or selected_default_domains)


def _build_eval_loop(
    *,
    workspace: Path,
    mode: str,
    domains: list[str],
) -> AgentLoop:
    cfg = Config(tools=ToolsConfig(tool_exposure=ToolExposureConfig(mode=mode, domains=domains)))
    return AgentLoop(
        bus=MessageBus(),
        provider=EvalDummyProvider(),
        workspace=workspace,
        config=cfg,
    )


def _evaluate_case_reasons(
    *,
    case: dict[str, Any],
    mode: str,
    snapshot: Any,
    visible_tools: set[str],
    available_tools: set[str],
) -> list[str]:
    reasons: list[str] = []
    if mode != "off":
        expected_domains = set(case.get("expected_auto_domains") or [])
        actual_domains = set(snapshot.selected_domains)
        if actual_domains != expected_domains:
            reasons.append(
                "selected_domains mismatch: "
                f"expected={sorted(expected_domains)} actual={sorted(actual_domains)}"
            )
    for tool_name in case.get("expect_tools_present", []):
        if tool_name in available_tools and tool_name not in visible_tools:
            reasons.append(f"missing tool: {tool_name}")
    for tool_name in case.get("expect_tools_absent", []):
        if tool_name in available_tools and tool_name in visible_tools:
            reasons.append(f"unexpected tool: {tool_name}")
    return reasons


def _build_case_result(request: CaseResultRequest) -> dict[str, Any]:
    return {
        "case_id": str(request.case.get("id") or ""),
        "passed": not request.reasons,
        "mode": request.mode,
        "domains": request.domains,
        "selected_domains": request.selected_domains,
        "visible_tool_count": request.visible_tool_count,
        "prompt_chars": request.prompt_chars,
        "reasons": request.reasons,
    }


def _evaluate_case(
    *,
    workspace: Path,
    case: dict[str, Any],
    selected_default_domains: list[str],
    mode_override: str | None,
    domains_override: list[str] | None,
) -> CaseEvaluationOutcome:
    mode = _resolve_case_mode(case, mode_override)
    domains = _resolve_case_domains(
        case,
        selected_default_domains=selected_default_domains,
        domains_override=domains_override,
    )
    loop = _build_eval_loop(workspace=workspace, mode=mode, domains=domains)
    snapshot = loop._build_tool_exposure_snapshot(
        initial_messages=[
            {"role": "system", "content": "tool exposure eval"},
            {"role": "user", "content": str(case.get("input") or "")},
        ],
        tool_signal_text=None,
        force_final_response=False,
    )
    visible_tools = (
        set(loop.tools.tool_names) if snapshot.full_exposure else set(snapshot.ordered_tool_names)
    )
    available_tools = set(loop.tools.tool_names)
    prompt_chars = sum(len(line) for line in snapshot.available_tool_lines)
    reasons = _evaluate_case_reasons(
        case=case,
        mode=mode,
        snapshot=snapshot,
        visible_tools=visible_tools,
        available_tools=available_tools,
    )
    return CaseEvaluationOutcome(
        result=_build_case_result(
            CaseResultRequest(
                case=case,
                mode=mode,
                domains=domains,
                selected_domains=list(snapshot.selected_domains),
                visible_tool_count=len(visible_tools),
                prompt_chars=prompt_chars,
                reasons=reasons,
            )
        ),
        visible_tool_count=len(visible_tools),
        prompt_chars=prompt_chars,
    )


def _build_eval_summary(request: EvalSummaryRequest) -> dict[str, Any]:
    total_cases = len(request.case_results)
    passed_cases = sum(1 for item in request.case_results if item["passed"])
    failed_cases = total_cases - passed_cases
    return {
        "run_id": request.run_id,
        "mode": request.mode_override or "mixed",
        "domains": list(request.domains_override or request.selected_default_domains),
        "summary": {
            "total_cases": total_cases,
            "passed": passed_cases,
            "failed": failed_cases,
            "pass_rate": (passed_cases / total_cases) if total_cases else 0.0,
        },
        "metrics": {
            "visible_tool_count_avg": (request.visible_tool_total / total_cases)
            if total_cases
            else 0.0,
            "avg_prompt_chars": (request.prompt_chars_total / total_cases) if total_cases else 0.0,
        },
        "failures": request.failures,
        "cases": request.case_results,
    }


def evaluate_tool_exposure_cases(
    *,
    workspace: Path,
    cases: list[dict[str, Any]],
    default_domains: list[str] | None = None,
    mode_override: str | None = None,
    domains_override: list[str] | None = None,
) -> dict[str, Any]:
    os.environ.setdefault("BRAVE_API_KEY", "tool-exposure-eval")
    selected_default_domains = list(default_domains or _DEFAULT_TOOL_EXPOSURE_DOMAINS)
    run_id = datetime.now().isoformat(timespec="seconds")
    case_results: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    visible_tool_total = 0
    prompt_chars_total = 0

    for case in cases:
        outcome = _evaluate_case(
            workspace=workspace,
            case=case,
            selected_default_domains=selected_default_domains,
            mode_override=mode_override,
            domains_override=domains_override,
        )
        visible_tool_total += outcome.visible_tool_count
        prompt_chars_total += outcome.prompt_chars
        case_results.append(outcome.result)
        if not outcome.result["passed"]:
            failures.append(
                {
                    "case_id": outcome.result["case_id"],
                    "reason": "; ".join(outcome.result["reasons"]),
                }
            )
    return _build_eval_summary(
        EvalSummaryRequest(
            run_id=run_id,
            case_results=case_results,
            failures=failures,
            visible_tool_total=visible_tool_total,
            prompt_chars_total=prompt_chars_total,
            mode_override=mode_override,
            domains_override=domains_override,
            selected_default_domains=selected_default_domains,
        )
    )


def write_tool_exposure_eval_artifact(output_dir: Path, payload: dict[str, Any]) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = output_dir / f"tool_exposure_eval_{stamp}.json"
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return target
