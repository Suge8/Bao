#!/usr/bin/env python3
"""Measure system prompt component sizes after optimization."""

import json
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def measure_skills_summary():
    """Measure skills summary size (B optimization)."""
    from bao.agent.skills import SkillsLoader

    workspace = Path.home() / ".bao" / "workspace"
    if not workspace.exists():
        workspace = Path("/tmp/_bao_measure")
        workspace.mkdir(exist_ok=True)

    loader = SkillsLoader(workspace)
    summary = loader.build_skills_summary()
    return summary


def measure_tool_schemas():
    """Measure tool schema sizes (C+D optimization)."""
    from bao.agent.tools.coding_agent import CodingAgentDetailsTool, CodingAgentTool

    workspace = Path.home() / ".bao" / "workspace"
    if not workspace.exists():
        workspace = Path("/tmp/_bao_measure")
        workspace.mkdir(exist_ok=True)

    coding_tool = CodingAgentTool(workspace=workspace)
    results = {}

    if coding_tool.available_backends:
        # Unified coding_agent tool schema
        schema = {
            "name": coding_tool.name,
            "description": coding_tool.description,
            "parameters": coding_tool.parameters,
        }
        schema_json = json.dumps(schema, ensure_ascii=False)
        results["coding_agent"] = {
            "chars": len(schema_json),
            "backends": coding_tool.available_backends,
        }

        # Details tool
        details = CodingAgentDetailsTool(coding_tool)
        details_schema = {
            "name": details.name,
            "description": details.description,
            "parameters": details.parameters,
        }
        details_json = json.dumps(details_schema, ensure_ascii=False)
        results["coding_agent_details"] = {"chars": len(details_json)}

        results["total_unified"] = (
            results["coding_agent"]["chars"] + results["coding_agent_details"]["chars"]
        )

        # Estimate old 6-tool size (each backend had its own tool + details)
        n_backends = len(coding_tool.available_backends)
        # Old: each tool ~800 chars schema + each details ~400 chars
        results["estimated_old_total"] = n_backends * (800 + 400)
    else:
        results["note"] = "No coding backends available"

    return results


def measure_memory_budget():
    """Measure memory injection budget (A optimization)."""
    from bao.agent.context import MAX_LONG_TERM_MEMORY_CHARS
    from bao.agent.memory import MEMORY_CATEGORY_CAPS, MemoryStore

    workspace = Path.home() / ".bao" / "workspace"
    if not workspace.exists():
        workspace = Path("/tmp/_bao_measure")
        workspace.mkdir(exist_ok=True)

    store = MemoryStore(workspace)

    # Read actual memory
    unbounded = store.get_memory_context(max_chars=None)
    bounded = store.get_memory_context(max_chars=MAX_LONG_TERM_MEMORY_CHARS)

    return {
        "MAX_LONG_TERM_MEMORY_CHARS": MAX_LONG_TERM_MEMORY_CHARS,
        "MEMORY_CATEGORY_CAPS": MEMORY_CATEGORY_CAPS,
        "unbounded_chars": len(unbounded),
        "bounded_chars": len(bounded),
        "savings": len(unbounded) - len(bounded),
    }


def measure_all_tool_descriptions():
    """Measure all built-in tool description lengths."""
    from bao.agent.tools.message import MessageTool

    # Tools that can be instantiated without complex deps
    simple_tools: list[tuple[str, str]] = []

    msg = MessageTool()
    simple_tools.append(("message", msg.description))

    # spawn and check_tasks need a manager, just read description directly
    simple_tools.append(("spawn", "Delegate a task to a background subagent. Returns task_id for tracking."))
    simple_tools.append(("check_tasks", "Check status of background tasks (by task_id or list all)."))
    simple_tools.append(("cancel_task", "Cancel a running background task by task_id."))

    return {name: {"description": desc, "chars": len(desc)} for name, desc in simple_tools}


def measure_full_system_prompt():
    """Measure the full assembled system prompt."""
    from bao.agent.context import ContextBuilder

    workspace = Path.home() / ".bao" / "workspace"
    if not workspace.exists():
        print("  [SKIP] No workspace found, cannot measure full prompt")
        return None

    builder = ContextBuilder(workspace)
    prompt = builder.build_system_prompt(channel="telegram", chat_id="test")
    return {
        "total_chars": len(prompt),
        "sections": [],
    }


def main():
    print("=" * 60)
    print("BAO SYSTEM PROMPT SIZE MEASUREMENT")
    print("=" * 60)

    # 1. Skills summary
    print("\n--- B: Skills Summary Compression ---")
    summary = measure_skills_summary()
    if summary:
        lines = summary.strip().split("\n")
        print(f"  Total chars: {len(summary)}")
        print(f"  Total lines: {len(lines)}")
        print("  Sample (first 3 lines):")
        for line in lines[:3]:
            print(f"    {line}")
        print("    ...")
    else:
        print("  [EMPTY] No skills found")

    # 2. Tool schemas
    print("\n--- C: Coding Agent Tool Merge (6→2) ---")
    tool_results = measure_tool_schemas()
    for k, v in tool_results.items():
        print(f"  {k}: {v}")

    # 3. Tool descriptions
    print("\n--- D: Tool Description MVD ---")
    desc_results = measure_all_tool_descriptions()
    for name, info in desc_results.items():
        print(f"  {name}: {info['chars']} chars → \"{info['description']}\"")

    # 4. Memory budget
    print("\n--- A: Memory Injection Budget ---")
    mem_results = measure_memory_budget()
    for k, v in mem_results.items():
        print(f"  {k}: {v}")

    # 5. Full system prompt
    print("\n--- Full System Prompt ---")
    prompt_result = measure_full_system_prompt()
    if prompt_result:
        print(f"  Total chars: {prompt_result['total_chars']}")

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    skills_chars = len(summary) if summary else 0
    unified_tools = tool_results.get("total_unified", 0)
    old_tools = tool_results.get("estimated_old_total", 0)
    mem_bounded = mem_results.get("bounded_chars", 0)
    mem_unbounded = mem_results.get("unbounded_chars", 0)

    print(f"  Skills summary:     {skills_chars:>5} chars (was ~2500 multi-line)")
    print(f"  Coding tools:       {unified_tools:>5} chars (was ~{old_tools} for {tool_results.get('coding_agent', {}).get('backends', [])} backends)")
    print(f"  Memory (bounded):   {mem_bounded:>5} chars (unbounded: {mem_unbounded})")
    if prompt_result:
        print(f"  Full system prompt: {prompt_result['total_chars']:>5} chars")


if __name__ == "__main__":
    main()
