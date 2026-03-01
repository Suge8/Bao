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
    from bao.providers.base import LLMProvider, LLMResponse
    from bao.session.manager import SessionManager

    class _DummyProvider(LLMProvider):
        async def chat(
            self,
            messages: list[dict[str, Any]],
            tools: list[dict[str, Any]] | None = None,
            model: str | None = None,
            max_tokens: int = 4096,
            temperature: float = 0.1,
            on_progress=None,
            **kwargs: Any,
        ) -> LLMResponse:
            del messages, tools, model, max_tokens, temperature, on_progress, kwargs
            return LLMResponse(content="ok")

        def get_default_model(self) -> str:
            return "openai/gpt-4o"

    workspace = _get_workspace()
    loop = AgentLoop(
        bus=MessageBus(),
        provider=_DummyProvider(),
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
    from bao.config.loader import _strip_jsonc_comments

    config_path = Path.home() / ".bao" / "config.jsonc"
    if not config_path.exists():
        return {"config_found": False, "mcp_server_count": 0, "mcp_server_names": []}

    text = config_path.read_text(encoding="utf-8")
    try:
        cleaned = _strip_jsonc_comments(text)
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
    from bao.agent.context import ContextBuilder

    builder = ContextBuilder(_get_workspace())
    identity = builder._get_identity(model=None, channel="telegram", chat_id="test")
    bootstrap = builder._load_bootstrap_files()
    always_skills = builder.skills.get_always_skills()
    active_skills = builder.skills.load_skills_for_context(always_skills) if always_skills else ""
    summary = builder.skills.build_skills_summary()
    response_format = builder.get_channel_format_hint("telegram") or ""
    total_prompt = builder.build_system_prompt(channel="telegram", chat_id="test")

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
    from bao.agent.context import ContextBuilder

    prompt = ContextBuilder(_get_workspace()).build_system_prompt(
        channel="telegram", chat_id="test"
    )
    return {
        "total_chars": len(prompt),
        "total_est_tokens": _estimate_tokens(len(prompt)),
    }


def main() -> None:
    print("=" * 60)
    print("BAO PROMPT/SCHEMA SIZE MEASUREMENT")
    print("=" * 60)

    print("\n--- Skills Summary ---")
    summary = measure_skills_summary()
    if summary:
        lines = summary.strip().split("\n")
        print(f"  Total chars: {len(summary)}")
        print(f"  Est tokens: {_estimate_tokens(len(summary))}")
        print(f"  Total lines: {len(lines)}")
        print("  Sample (first 3 lines):")
        for line in lines[:3]:
            print(f"    {line}")
        print("    ...")
    else:
        print("  [EMPTY] No skills found")

    print("\n--- Coding Tool Schema (6→2 optimization) ---")
    coding = measure_coding_tool_schemas()
    for k, v in coding.items():
        print(f"  {k}: {v}")

    print("\n--- Runtime Tool Schema Payload ---")
    runtime_tools = measure_registered_tool_schemas()
    print(f"  Tool count: {runtime_tools['tool_count']}")
    print(f"  Schema chars: {runtime_tools['schema_chars']}")
    print(f"  Est tokens: {runtime_tools['schema_est_tokens']}")
    print(f"  Tool names: {runtime_tools['tool_names']}")

    print("\n--- MCP Config State ---")
    mcp_state = measure_mcp_config_state()
    for k, v in mcp_state.items():
        print(f"  {k}: {v}")

    print("\n--- Memory Budget ---")
    mem = measure_memory_budget()
    for k, v in mem.items():
        print(f"  {k}: {v}")

    print("\n--- Full System Prompt ---")
    full_prompt = measure_full_system_prompt()
    print(f"  Total chars: {full_prompt['total_chars']}")
    print(f"  Est tokens: {full_prompt['total_est_tokens']}")

    print("\n--- Full System Prompt Breakdown ---")
    breakdown = measure_system_prompt_breakdown()
    print(f"  total_chars: {breakdown['total_chars']}")
    print(f"  total_est_tokens: {breakdown['total_est_tokens']}")
    print(f"  always_skill_count: {breakdown['always_skill_count']}")
    for section, chars in breakdown["sections"].items():
        print(f"  {section}: {chars} chars (~{_estimate_tokens(chars)} tokens)")
    print(f"  joiner_and_headers_overhead: {breakdown['joiner_and_headers_overhead']} chars")

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


if __name__ == "__main__":
    main()
