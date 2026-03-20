from __future__ import annotations

import asyncio
from typing import Any

from loguru import logger

from bao.agent.tool_result import ToolResultValue, maybe_temp_text_result
from bao.agent.tools._mcp_common import (
    neutral_metadata_hint,
    normalize_name_fragment,
    reached_global_cap,
    reached_server_cap,
    slim_schema,
    truncate_description,
)
from bao.agent.tools._mcp_wrapper_models import (
    BuildPendingWrappersRequest,
    MCPToolWrapperSpec,
    RegisterPendingWrappersRequest,
)
from bao.agent.tools.base import Tool
from bao.agent.tools.registry import ToolMetadata, ToolRegistry


def reserve_wrapper_name(
    *,
    server_name: str,
    tool_name: str,
    pending_names: set[str],
    registry: ToolRegistry,
) -> str:
    server_part = normalize_name_fragment(server_name, "server")
    tool_part = normalize_name_fragment(tool_name, "tool")
    base_name = f"mcp_{server_part}_{tool_part}"[:64]
    wrapper_name = base_name
    collision_index = 1
    while wrapper_name in pending_names or registry.has(wrapper_name):
        suffix = f"_{collision_index}"
        wrapper_name = f"{base_name[: max(1, 64 - len(suffix))]}{suffix}"
        collision_index += 1
    pending_names.add(wrapper_name)
    return wrapper_name


class MCPToolWrapper(Tool):
    """Wraps a single MCP server tool as a Bao Tool."""

    def __init__(self, session, spec: MCPToolWrapperSpec):
        self._session = session
        self._original_name = spec.tool_def.name
        self._name = spec.name_override or f"mcp_{spec.server_name}_{spec.tool_def.name}"
        description = (
            spec.tool_def.description
            if isinstance(spec.tool_def.description, str)
            else spec.tool_def.name
        )
        raw_schema = spec.tool_def.inputSchema
        parameters = raw_schema if isinstance(raw_schema, dict) else {"type": "object", "properties": {}}
        if spec.slim_schema:
            self._description = truncate_description(description)
            self._parameters = slim_schema_fn(parameters)
        else:
            self._description = description
            self._parameters = parameters
        self._timeout = spec.timeout if isinstance(spec.timeout, int) and spec.timeout > 0 else 30

    @property
    def original_name(self) -> str:
        return self._original_name

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def parameters(self) -> dict[str, Any]:
        return self._parameters

    async def execute(self, **kwargs: Any) -> ToolResultValue:
        from mcp import types

        try:
            result = await asyncio.wait_for(
                self._session.call_tool(self._original_name, arguments=kwargs),
                timeout=self._timeout,
            )
        except asyncio.TimeoutError:
            return f"Error: MCP tool '{self._original_name}' timed out after {self._timeout}s"
        except asyncio.CancelledError:
            task = asyncio.current_task()
            if task is not None and task.cancelling() > 0:
                raise
            logger.warning("⚠️ MCP 调用被取消 / tool call cancelled: {}:{}", self._name, self._original_name)
            return f"Error: MCP tool '{self._original_name}' was cancelled"
        except Exception as exc:
            logger.warning("⚠️ MCP 调用失败 / tool call failed: {}:{} {}", self._name, self._original_name, exc)
            return f"Error: MCP tool '{self._original_name}' failed: {type(exc).__name__}"

        parts = []
        for block in result.content:
            if isinstance(block, types.TextContent):
                parts.append(block.text)
            else:
                parts.append(str(block))
        return maybe_temp_text_result("\n".join(parts) or "(no output)", prefix="bao_mcp_tool_")


def slim_schema_fn(parameters: dict[str, Any]) -> dict[str, Any]:
    return slim_schema(parameters)


def build_pending_wrappers(request: BuildPendingWrappersRequest) -> list[MCPToolWrapper]:
    server_count = 0
    pending_names: set[str] = set()
    pending_wrappers: list[MCPToolWrapper] = []

    for tool_def in request.tool_defs:
        if reached_global_cap(request.total_registered, len(pending_wrappers), request.max_tools):
            logger.debug("🔌 MCP 达到上限 / limit reached: ({}) while registering {}", request.max_tools, request.server_name)
            break
        if reached_server_cap(server_count, len(pending_wrappers), request.server_max_tools):
            logger.debug("🔌 MCP 服务器达到上限 / server limit reached: {} ({} tools)", request.server_name, request.server_max_tools)
            break
        wrapper_name = reserve_wrapper_name(
            server_name=request.server_name,
            tool_name=str(tool_def.name),
            pending_names=pending_names,
            registry=request.registry,
        )
        pending_wrappers.append(
            MCPToolWrapper(
                request.session,
                MCPToolWrapperSpec(
                    server_name=request.server_name,
                    tool_def=tool_def,
                    timeout=request.tool_timeout,
                    slim_schema=request.server_slim_schema,
                    name_override=wrapper_name,
                ),
            )
        )
    return pending_wrappers


def register_pending_wrappers(request: RegisterPendingWrappersRequest) -> tuple[int, int]:
    server_count = 0
    registered_names: list[str] = []
    total_registered = request.total_registered
    try:
        for wrapper in request.pending_wrappers:
            if reached_global_cap(total_registered, 0, request.max_tools):
                break
            if reached_server_cap(server_count, 0, request.server_max_tools):
                break
            neutral_hint = neutral_metadata_hint(wrapper.original_name)
            request.registry.register(
                wrapper,
                metadata=ToolMetadata(
                    bundle="core",
                    short_hint=neutral_hint,
                    aliases=(wrapper.original_name,),
                    keyword_aliases=(),
                    auto_callable=True,
                    summary=neutral_hint,
                ),
            )
            registered_names.append(wrapper.name)
            total_registered += 1
            server_count += 1
            logger.debug("MCP: registered tool '{}' from server '{}'", wrapper.name, request.server_name)
    except Exception:
        for tool_name in registered_names:
            request.registry.unregister(tool_name)
        raise
    return server_count, total_registered
