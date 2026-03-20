from __future__ import annotations

import asyncio
from contextlib import AsyncExitStack
from dataclasses import dataclass
from typing import Any

from loguru import logger

from bao.agent.tools._mcp_common import (
    reached_global_cap as _reached_global_cap,
)
from bao.agent.tools._mcp_common import (
    resolve_server_max_tools as _resolve_server_max_tools,
)
from bao.agent.tools._mcp_common import (
    resolve_server_slim_schema as _resolve_server_slim_schema,
)
from bao.agent.tools._mcp_common import (
    resolve_tool_timeout_seconds as _resolve_tool_timeout_seconds,
)
from bao.agent.tools._mcp_common import (
    resolve_transport_type as _resolve_transport_type,
)
from bao.agent.tools._mcp_transport import (
    close_stack_quietly as _close_stack_quietly,
)
from bao.agent.tools._mcp_transport import (
    open_server_streams as _open_server_streams,
)
from bao.agent.tools._mcp_wrapper import (
    build_pending_wrappers as _build_pending_wrappers,
)
from bao.agent.tools._mcp_wrapper import (
    register_pending_wrappers as _register_pending_wrappers,
)
from bao.agent.tools._mcp_wrapper_models import (
    BuildPendingWrappersRequest,
    RegisterPendingWrappersRequest,
)
from bao.agent.tools.registry import ToolRegistry


@dataclass(slots=True)
class MCPServerConnectRequest:
    name: str
    cfg: Any
    registry: ToolRegistry
    total_registered: int
    max_tools: int
    default_slim_schema: bool


@dataclass(slots=True)
class MCPServerConnectResult:
    connected: bool
    registered_tools: int
    total_registered: int
    server_stack: AsyncExitStack | None = None


async def connect_single_mcp_server(request: MCPServerConnectRequest) -> MCPServerConnectResult:
    from mcp import ClientSession

    if _reached_global_cap(request.total_registered, 0, request.max_tools):
        logger.debug("🔌 MCP 达到上限 / limit reached: global tool limit ({})", request.max_tools)
        return MCPServerConnectResult(
            connected=False,
            registered_tools=0,
            total_registered=request.total_registered,
        )

    name = request.name
    cfg = request.cfg
    server_stack = AsyncExitStack()
    await server_stack.__aenter__()
    try:
        transport_type = _resolve_transport_type(cfg)
        if transport_type is None:
            logger.warning("⚠️ MCP 配置缺失 / config missing: {} has no command/url, skipping", name)
            return await _close_result_stack(server_stack, request.total_registered)

        timeout = _resolve_tool_timeout_seconds(cfg)
        streams = await _open_server_streams(cfg, server_stack, timeout)
        if streams is None:
            logger.warning("⚠️ MCP 传输无效 / invalid transport: {} type={}", name, transport_type)
            return await _close_result_stack(server_stack, request.total_registered)

        read, write = streams
        session = await server_stack.enter_async_context(ClientSession(read, write))
        await asyncio.wait_for(session.initialize(), timeout=timeout)
        tools = await asyncio.wait_for(session.list_tools(), timeout=timeout)
        registration = _register_server_tools(
            request=request,
            cfg=cfg,
            session=session,
            tool_defs=tools.tools,
            timeout=timeout,
        )
        server_count = registration.registered_tools
        total_registered = registration.total_registered
        if server_count <= 0:
            logger.debug("MCP connected but no tools registered for server '{}': cap or empty list", name)
            return await _close_result_stack(server_stack, total_registered, connected=True)

        logger.info("🔌 MCP 已连接 / connected: {} ({} tools)", name, server_count)
        return MCPServerConnectResult(
            connected=True,
            registered_tools=server_count,
            total_registered=total_registered,
            server_stack=server_stack,
        )
    except asyncio.CancelledError:
        await _close_stack_quietly(server_stack)
        raise
    except Exception as exc:
        logger.error("❌ MCP 连接失败 / connect failed: {} — {}", name, exc)
        return await _close_result_stack(server_stack, request.total_registered)


def _register_server_tools(
    *,
    request: MCPServerConnectRequest,
    cfg: Any,
    session: Any,
    tool_defs: list[Any],
    timeout: int,
) -> MCPServerConnectResult:
    pending_wrappers = _build_pending_wrappers(
        BuildPendingWrappersRequest(
            session=session,
            server_name=request.name,
            tool_defs=tool_defs,
            registry=request.registry,
            total_registered=request.total_registered,
            max_tools=request.max_tools,
            server_max_tools=_resolve_server_max_tools(cfg),
            tool_timeout=timeout,
            server_slim_schema=_resolve_server_slim_schema(cfg, request.default_slim_schema),
        )
    )
    server_count, total_registered = _register_pending_wrappers(
        RegisterPendingWrappersRequest(
            pending_wrappers=pending_wrappers,
            registry=request.registry,
            total_registered=request.total_registered,
            max_tools=request.max_tools,
            server_max_tools=_resolve_server_max_tools(cfg),
            server_name=request.name,
        )
    )
    return MCPServerConnectResult(
        connected=server_count > 0,
        registered_tools=server_count,
        total_registered=total_registered,
    )


async def _close_result_stack(
    server_stack: AsyncExitStack,
    total_registered: int,
    *,
    connected: bool = False,
) -> MCPServerConnectResult:
    await _close_stack_quietly(server_stack)
    return MCPServerConnectResult(
        connected=connected,
        registered_tools=0,
        total_registered=total_registered,
    )
