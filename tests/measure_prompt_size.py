#!/usr/bin/env python3
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent))


def _estimate_tokens(chars: int) -> int:
    return max(0, chars // 4)


def _get_workspace() -> Path:
    workspace = Path.home() / ".bao" / "workspace"
    if workspace.exists():
        return workspace
    fallback = Path("/tmp/_bao_measure")
    fallback.mkdir(exist_ok=True)
    return fallback


def _extract_tool_name(tool_def: dict[str, Any]) -> str:
    if "function" in tool_def and isinstance(tool_def["function"], dict):
        return str(tool_def["function"].get("name") or "")
    return str(tool_def.get("name") or "")


class _MeasureProvider:
    async def chat(self, *_args: Any, **_kwargs: Any):
        from bao.providers.base import LLMResponse

        return LLMResponse(content="ok")

    def get_default_model(self) -> str:
        return "openai/gpt-4o"


def _print_mapping(title: str, values: dict[str, Any]) -> None:
    print(f"\n--- {title} ---")
    for key, value in values.items():
        print(f"  {key}: {value}")


def _print_skills_summary(summary: str) -> None:
    print("\n--- Skills Summary ---")
    if not summary:
        print("  [EMPTY] No skills found")
        return
    lines = summary.strip().split("\n")
    print(f"  Total chars: {len(summary)}")
    print(f"  Est tokens: {_estimate_tokens(len(summary))}")
    print(f"  Total lines: {len(lines)}")
    print("  Sample (first 3 lines):")
    for line in lines[:3]:
        print(f"    {line}")
    print("    ...")


def _print_prompt_breakdown(breakdown: dict[str, Any]) -> None:
    print("\n--- Full System Prompt Breakdown ---")
    print(f"  total_chars: {breakdown['total_chars']}")
    print(f"  total_est_tokens: {breakdown['total_est_tokens']}")
    print(f"  always_skill_count: {breakdown['always_skill_count']}")
    for section, chars in breakdown["sections"].items():
        print(f"  {section}: {chars} chars (~{_estimate_tokens(chars)} tokens)")
    print(f"  joiner_and_headers_overhead: {breakdown['joiner_and_headers_overhead']} chars")


def _print_summary_footer(report: dict[str, Any]) -> None:
    summary = report["summary"]
    coding = report["coding"]
    runtime_tools = report["runtime_tools"]
    mem = report["mem"]
    full_prompt = report["full_prompt"]
    mcp_state = report["mcp_state"]
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(
        f"  Skills summary:      {len(summary):>5} chars (~{_estimate_tokens(len(summary))} tokens)"
    )
    print(
        "  Coding tools:        "
        f"{coding.get('total_unified', 0):>5} chars "
        f"(was ~{coding.get('estimated_old_total', 0)})"
    )
    print(
        "  Runtime tool schema: "
        f"{runtime_tools['schema_chars']:>5} chars "
        f"({runtime_tools['tool_count']} tools)"
    )
    print(
        "  Memory (bounded):    "
        f"{mem.get('bounded_chars', 0):>5} chars "
        f"(unbounded: {mem.get('unbounded_chars', 0)})"
    )
    print(
        "  Full system prompt:  "
        f"{full_prompt['total_chars']:>5} chars "
        f"(~{full_prompt['total_est_tokens']} tokens)"
    )
    print(f"  MCP servers configured: {mcp_state.get('mcp_server_count', 0)}")


def measure_skills_summary() -> str:
    from bao.agent.skills import SkillsLoader

    loader = SkillsLoader(_get_workspace())
    return loader.build_skills_summary()


def measure_coding_tool_schemas() -> dict[str, Any]:
    from bao.agent.tools.coding_agent import CodingAgentDetailsTool, CodingAgentTool

    coding_tool = CodingAgentTool(workspace=_get_workspace())
    results: dict[str, Any] = {}

    if coding_tool.available_backends:
        schema = {
            "name": coding_tool.name,
            "description": coding_tool.description,
            "parameters": coding_tool.parameters,
        }
        details = CodingAgentDetailsTool(coding_tool)
        details_schema = {
            "name": details.name,
            "description": details.description,
            "parameters": details.parameters,
        }
        coding_chars = len(json.dumps(schema, ensure_ascii=False))
        details_chars = len(json.dumps(details_schema, ensure_ascii=False))

        results["coding_agent"] = {
            "chars": coding_chars,
            "backends": coding_tool.available_backends,
        }
        results["coding_agent_details"] = {"chars": details_chars}
        results["total_unified"] = coding_chars + details_chars

        n_backends = len(coding_tool.available_backends)
        results["estimated_old_total"] = n_backends * (800 + 400)
    else:
        results["note"] = "No coding backends available"

    return results


def measure_memory_budget() -> dict[str, Any]:
    from bao.agent.context import MAX_LONG_TERM_MEMORY_CHARS
    from bao.agent.memory import MEMORY_CATEGORY_CAPS, MemoryStore

    store = MemoryStore(_get_workspace())
    unbounded = store.get_memory_context(max_chars=None)
    bounded = store.get_memory_context(max_chars=MAX_LONG_TERM_MEMORY_CHARS)

    return {
        "MAX_LONG_TERM_MEMORY_CHARS": MAX_LONG_TERM_MEMORY_CHARS,
        "MEMORY_CATEGORY_CAPS": MEMORY_CATEGORY_CAPS,
        "unbounded_chars": len(unbounded),
        "bounded_chars": len(bounded),
        "savings": len(unbounded) - len(bounded),
    }


def measure_registered_tool_schemas() -> dict[str, Any]:
    from bao.agent.loop import AgentLoop
    from bao.bus.queue import MessageBus
    from bao.session.manager import SessionManager

    workspace = _get_workspace()
    loop = AgentLoop(
        bus=MessageBus(),
        provider=_MeasureProvider(),
        workspace=workspace,
        model="openai/gpt-4o",
        config=None,
        session_manager=SessionManager(workspace),
    )
    definitions = loop.tools.get_definitions()
    payload = json.dumps(definitions, ensure_ascii=False)
    tool_names = sorted(_extract_tool_name(item) for item in definitions if isinstance(item, dict))
    return {
        "tool_count": len(definitions),
        "schema_chars": len(payload),
        "schema_est_tokens": _estimate_tokens(len(payload)),
        "tool_names": tool_names,
    }


def measure_mcp_config_state() -> dict[str, Any]:
    from bao.config.loader import strip_jsonc_comments

    config_path = Path.home() / ".bao" / "config.jsonc"
    if not config_path.exists():
        return {"config_found": False, "mcp_server_count": 0, "mcp_server_names": []}

    text = config_path.read_text(encoding="utf-8")
    try:
        cleaned = strip_jsonc_comments(text)
        data = json.loads(cleaned)
    except Exception as e:
        return {
            "config_found": True,
            "parse_error": str(e),
            "mcp_server_count": 0,
            "mcp_server_names": [],
        }

    tools_cfg = data.get("tools", {}) if isinstance(data, dict) else {}
    servers = tools_cfg.get("mcpServers", {}) if isinstance(tools_cfg, dict) else {}
    if not isinstance(servers, dict):
        servers = {}
    return {
        "config_found": True,
        "mcp_server_count": len(servers),
        "mcp_server_names": sorted(servers.keys()),
    }


def measure_system_prompt_breakdown() -> dict[str, Any]:
    from bao.agent.context import ContextBuilder, SystemPromptRequest

    builder = ContextBuilder(_get_workspace())
    identity = builder._get_identity(request=SystemPromptRequest(model=None, channel="telegram", chat_id="test"))
    bootstrap = builder._load_bootstrap_files()
    always_skills = builder.skills.get_always_skills()
    active_skills = builder.skills.load_skills_for_context(always_skills) if always_skills else ""
    summary = builder.skills.build_skills_summary()
    response_format = builder.get_channel_format_hint("telegram") or ""
    total_prompt = builder.build_system_prompt(SystemPromptRequest(channel="telegram", chat_id="test"))

    sections = {
        "identity_runtime_workspace": len(identity),
        "bootstrap_persona_instructions": len(bootstrap),
        "active_skills_full_text": len(active_skills),
        "skills_summary_index": len(summary),
        "response_format_hint": len(response_format),
    }
    measured_sum = sum(sections.values())
    return {
        "total_chars": len(total_prompt),
        "total_est_tokens": _estimate_tokens(len(total_prompt)),
        "always_skill_count": len(always_skills),
        "sections": sections,
        "joiner_and_headers_overhead": max(0, len(total_prompt) - measured_sum),
    }


def measure_full_system_prompt() -> dict[str, Any]:
    from bao.agent.context import ContextBuilder, SystemPromptRequest

    prompt = ContextBuilder(_get_workspace()).build_system_prompt(
        SystemPromptRequest(channel="telegram", chat_id="test")
    )
    return {
        "total_chars": len(prompt),
        "total_est_tokens": _estimate_tokens(len(prompt)),
    }


def main() -> None:
    print("=" * 60)
    print("BAO PROMPT/SCHEMA SIZE MEASUREMENT")
    print("=" * 60)

    summary = measure_skills_summary()
    _print_skills_summary(summary)

    coding = measure_coding_tool_schemas()
    _print_mapping("Coding Tool Schema (6→2 optimization)", coding)

    runtime_tools = measure_registered_tool_schemas()
    _print_mapping("Runtime Tool Schema Payload", runtime_tools)

    mcp_state = measure_mcp_config_state()
    _print_mapping("MCP Config State", mcp_state)

    mem = measure_memory_budget()
    _print_mapping("Memory Budget", mem)

    full_prompt = measure_full_system_prompt()
    _print_mapping("Full System Prompt", full_prompt)

    breakdown = measure_system_prompt_breakdown()
    _print_prompt_breakdown(breakdown)
    _print_summary_footer(
        {
            "summary": summary,
            "coding": coding,
            "runtime_tools": runtime_tools,
            "mem": mem,
            "full_prompt": full_prompt,
            "mcp_state": mcp_state,
        }
    )


if __name__ == "__main__":
    main()
