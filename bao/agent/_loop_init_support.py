from __future__ import annotations

from typing import Any

from loguru import logger

from bao.agent._loop_init_models import LoopInitOptions
from bao.agent._tool_exposure_domains import normalize_tool_exposure_domains

_LOOP_INIT_OPTION_KEYS = frozenset(LoopInitOptions.__dataclass_fields__.keys())


def build_loop_init_options(kwargs: dict[str, Any]) -> LoopInitOptions:
    unknown_keys = sorted(set(kwargs) - _LOOP_INIT_OPTION_KEYS)
    if unknown_keys:
        unknown_text = ", ".join(unknown_keys)
        raise TypeError(f"Unexpected AgentLoop option(s): {unknown_text}")
    payload = dict(kwargs)
    return LoopInitOptions(**payload)


def normalize_available_models(
    *,
    model: str | None,
    available_models: list[str],
) -> list[str]:
    normalized = list(available_models)
    if model and model not in normalized:
        normalized.insert(0, model)
    return normalized


def resolve_agent_defaults(config: Any) -> Any:
    if config is None:
        return None
    agents = getattr(config, "agents", None)
    return getattr(agents, "defaults", None)


def resolve_subagent_manager_class(default_cls: type[Any]) -> type[Any]:
    from bao.agent import loop as loop_module

    candidate = getattr(loop_module, "SubagentManager", default_cls)
    return candidate if isinstance(candidate, type) else default_cls


def apply_context_management_defaults(loop: Any, defaults: Any) -> None:
    loop._ctx_mgmt = defaults.context_management if defaults else "auto"
    loop._tool_offload_chars = defaults.tool_output_offload_chars if defaults else 8000
    loop._tool_preview_chars = defaults.tool_output_preview_chars if defaults else 3000
    loop._tool_hard_chars = defaults.tool_output_hard_chars if defaults else 6000
    loop._compact_bytes = defaults.context_compact_bytes_est if defaults else 240000
    loop._compact_keep_blocks = (
        defaults.context_compact_keep_recent_tool_blocks if defaults else 4
    )
    loop._artifact_retention_days = defaults.artifact_retention_days if defaults else 7
    loop._artifact_cleanup_done = False


def apply_tool_config_defaults(loop: Any, config: Any) -> None:
    tools_cfg = getattr(config, "tools", None) if config else None
    loop._image_generation_config = getattr(tools_cfg, "image_generation", None)
    loop._desktop_config = getattr(tools_cfg, "desktop", None)
    web_cfg = getattr(tools_cfg, "web", None)
    web_browser_cfg = getattr(web_cfg, "browser", None) if web_cfg else None
    loop._web_browser_enabled = (
        getattr(web_browser_cfg, "enabled", True) if web_browser_cfg else True
    )


def configure_mcp_and_tool_exposure(loop: Any, config: Any, tool_domains: set[str]) -> None:
    tools_cfg = getattr(config, "tools", None) if config else None
    raw_mcp_max_tools = getattr(tools_cfg, "mcp_max_tools", 50)
    loop._mcp_max_tools = (
        max(raw_mcp_max_tools, 0)
        if isinstance(raw_mcp_max_tools, int) and not isinstance(raw_mcp_max_tools, bool)
        else 50
    )
    raw_mcp_slim_schema = getattr(tools_cfg, "mcp_slim_schema", True)
    loop._mcp_slim_schema = raw_mcp_slim_schema if isinstance(raw_mcp_slim_schema, bool) else True
    tool_exposure_cfg = getattr(tools_cfg, "tool_exposure", None)
    raw_mode = str(getattr(tool_exposure_cfg, "mode", "auto") or "auto").lower()
    loop._tool_exposure_mode = raw_mode if raw_mode in ("off", "auto") else "auto"
    domains = normalize_tool_exposure_domains(getattr(tool_exposure_cfg, "domains", None))
    loop._tool_exposure_domains = {item for item in domains if item in tool_domains}
    if not loop._tool_exposure_domains:
        loop._tool_exposure_domains = set(tool_domains)


def build_utility_provider(loop: Any, config: Any) -> Any:
    if not config or not config.agents.defaults.utility_model:
        return None
    try:
        from bao.providers import make_provider

        loop._utility_model = config.agents.defaults.utility_model
        provider = make_provider(config, loop._utility_model)
        logger.debug("Utility model configured: {}", loop._utility_model)
        return provider
    except Exception as exc:
        logger.warning("⚠️ 效用模型初始化失败 / utility init failed: {}", exc)
        return None
