"""MCP client facade: transport, wrapper, and connection entrypoints."""

from __future__ import annotations

import asyncio
from contextlib import AsyncExitStack
from typing import Any

from bao.agent.tools._mcp_common import (
    normalize_non_bool_int as _normalize_non_bool_int,
)
from bao.agent.tools._mcp_common import (
    reached_global_cap as _reached_global_cap,
)
from bao.agent.tools._mcp_common import (
    reached_server_cap as _reached_server_cap,
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
from bao.agent.tools._mcp_common import (
    slim_schema as _slim_schema,
)
from bao.agent.tools._mcp_common import (
    truncate_description as _truncate_description,
)
from bao.agent.tools._mcp_connection import (
    MCPServerConnectRequest,
)
from bao.agent.tools._mcp_connection import (
    connect_single_mcp_server as _connect_single_mcp_server,
)
from bao.agent.tools._mcp_transport import (
    close_stack_quietly as _close_stack_quietly,
)
from bao.agent.tools._mcp_transport import (
    open_server_streams as _open_server_streams,
)
from bao.agent.tools._mcp_wrapper import (
    MCPToolWrapper,
)
from bao.agent.tools._mcp_wrapper import (
    build_pending_wrappers as _build_pending_wrappers,
)
from bao.agent.tools._mcp_wrapper import (
    register_pending_wrappers as _register_pending_wrappers,
)
from bao.agent.tools.registry import ToolRegistry


async def connect_mcp_servers(
    mcp_servers: dict[str, Any],
    registry: ToolRegistry,
    stack: AsyncExitStack,
    max_tools: int = 50,
    slim_schema: bool = True,
) -> tuple[int, int]:
    total_registered = 0
    connected_servers = 0

    for name, cfg in mcp_servers.items():
        if _reached_global_cap(total_registered, 0, max_tools):
            break
        result = await _connect_single_mcp_server(
            MCPServerConnectRequest(
                name=name,
                cfg=cfg,
                registry=registry,
                total_registered=total_registered,
                max_tools=max_tools,
                default_slim_schema=slim_schema,
            )
        )
        total_registered = result.total_registered
        if result.connected:
            connected_servers += 1
        if result.server_stack is not None:
            await stack.enter_async_context(result.server_stack)

    return total_registered, connected_servers


async def probe_mcp_server(
    server_name: str,
    cfg: Any,
    *,
    connect_timeout: int | None = None,
) -> dict[str, object]:
    from mcp import ClientSession

    timeout = connect_timeout or _resolve_tool_timeout_seconds(cfg)
    server_stack = AsyncExitStack()
    await server_stack.__aenter__()
    try:
        streams = await _open_server_streams(cfg, server_stack, timeout)
        if streams is None:
            return {
                "serverName": server_name,
                "canConnect": False,
                "toolNames": [],
                "error": "Missing command or URL.",
            }
        read, write = streams
        session = await server_stack.enter_async_context(ClientSession(read, write))
        await asyncio.wait_for(session.initialize(), timeout=timeout)
        tools = await asyncio.wait_for(session.list_tools(), timeout=timeout)
        return {
            "serverName": server_name,
            "canConnect": True,
            "toolNames": [str(tool.name) for tool in tools.tools],
            "error": "",
        }
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        return {
            "serverName": server_name,
            "canConnect": False,
            "toolNames": [],
            "error": str(exc),
        }
    finally:
        await _close_stack_quietly(server_stack)


__all__ = [
    "MCPToolWrapper",
    "_build_pending_wrappers",
    "_close_stack_quietly",
    "_normalize_non_bool_int",
    "_open_server_streams",
    "_reached_global_cap",
    "_reached_server_cap",
    "_register_pending_wrappers",
    "_resolve_server_max_tools",
    "_resolve_server_slim_schema",
    "_resolve_tool_timeout_seconds",
    "_resolve_transport_type",
    "_slim_schema",
    "_truncate_description",
    "connect_mcp_servers",
    "probe_mcp_server",
]
