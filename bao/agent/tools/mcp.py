"""MCP client: connects to MCP servers and wraps their tools as native Bao tools."""

import asyncio
from contextlib import AsyncExitStack
from typing import Any

import httpx
from loguru import logger

from bao.agent.tools.base import Tool
from bao.agent.tools.registry import ToolRegistry

_REMOVABLE_SCHEMA_KEYS = {"examples", "example", "default", "title", "$comment"}


def _truncate_description(text: str, max_chars: int = 150) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "..."


def _slim_schema(schema: Any, max_description_chars: int = 150) -> Any:
    if isinstance(schema, dict):
        result: dict[str, Any] = {}
        for key, value in schema.items():
            if key in _REMOVABLE_SCHEMA_KEYS:
                continue
            if key == "description" and isinstance(value, str):
                result[key] = _truncate_description(value, max_description_chars)
                continue
            result[key] = _slim_schema(value, max_description_chars)
        return result
    if isinstance(schema, list):
        return [_slim_schema(item, max_description_chars) for item in schema]
    return schema


def _normalize_non_bool_int(value: Any) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None


def _resolve_server_slim_schema(server_cfg: Any, default: bool) -> bool:
    raw_override = getattr(server_cfg, "slim_schema", None)
    return raw_override if isinstance(raw_override, bool) else default


def _resolve_server_max_tools(server_cfg: Any) -> int | None:
    raw_override = _normalize_non_bool_int(getattr(server_cfg, "max_tools", None))
    if raw_override is None:
        return None
    return max(raw_override, 0)


def _reached_global_cap(total_registered: int, pending_count: int, max_tools: int) -> bool:
    if max_tools <= 0:
        return False
    return (total_registered + pending_count) >= max_tools


def _reached_server_cap(
    server_count: int, pending_count: int, server_max_tools: int | None
) -> bool:
    if server_max_tools is None or server_max_tools <= 0:
        return False
    return (server_count + pending_count) >= server_max_tools


def _normalize_name_fragment(value: str, fallback: str) -> str:
    lowered = value.lower()
    chars = [ch if (ch.isalnum() or ch == "_") else "_" for ch in lowered]
    compact = "_".join(part for part in "".join(chars).split("_") if part)
    if not compact:
        compact = fallback
    if compact[0].isdigit():
        compact = f"n_{compact}"
    return compact[:32]


class MCPToolWrapper(Tool):
    """Wraps a single MCP server tool as a Bao Tool."""

    def __init__(
        self,
        session,
        server_name: str,
        tool_def,
        timeout: int = 30,
        slim_schema: bool = True,
        name_override: str | None = None,
    ):
        self._session = session
        self._original_name = tool_def.name
        self._name = name_override or f"mcp_{server_name}_{tool_def.name}"
        description = (
            tool_def.description if isinstance(tool_def.description, str) else tool_def.name
        )
        raw_schema = tool_def.inputSchema
        parameters = (
            raw_schema if isinstance(raw_schema, dict) else {"type": "object", "properties": {}}
        )
        if slim_schema:
            self._description = _truncate_description(description)
            self._parameters = _slim_schema(parameters)
        else:
            self._description = description
            self._parameters = parameters
        self._timeout = timeout if isinstance(timeout, int) and timeout > 0 else 30

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def parameters(self) -> dict[str, Any]:
        return self._parameters

    async def execute(self, **kwargs: Any) -> str:
        from mcp import types

        try:
            result = await asyncio.wait_for(
                self._session.call_tool(self._original_name, arguments=kwargs),
                timeout=self._timeout,
            )
        except asyncio.TimeoutError:
            return f"Error: MCP tool '{self._original_name}' timed out after {self._timeout}s"
        parts = []
        for block in result.content:
            if isinstance(block, types.TextContent):
                parts.append(block.text)
            else:
                parts.append(str(block))
        return "\n".join(parts) or "(no output)"


async def connect_mcp_servers(
    mcp_servers: dict[str, Any],
    registry: ToolRegistry,
    stack: AsyncExitStack,
    max_tools: int = 50,
    slim_schema: bool = True,
) -> tuple[int, int]:
    """Connect to configured MCP servers and register their tools."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    total_registered = 0
    connected_servers = 0

    for name, cfg in mcp_servers.items():
        if _reached_global_cap(total_registered, 0, max_tools):
            logger.debug(
                "🔌 MCP 达到上限 / limit reached: global tool limit ({})",
                max_tools,
            )
            break
        server_slim_schema = _resolve_server_slim_schema(cfg, slim_schema)
        server_max_tools = _resolve_server_max_tools(cfg)
        server_stack = AsyncExitStack()
        await server_stack.__aenter__()
        try:
            connect_timeout = (
                cfg.tool_timeout_seconds
                if isinstance(cfg.tool_timeout_seconds, int) and cfg.tool_timeout_seconds > 0
                else 30
            )
            tool_timeout = (
                cfg.tool_timeout_seconds
                if isinstance(cfg.tool_timeout_seconds, int) and cfg.tool_timeout_seconds > 0
                else 30
            )
            if cfg.command:
                params = StdioServerParameters(
                    command=cfg.command, args=cfg.args, env=cfg.env or None
                )
                read, write = await asyncio.wait_for(
                    server_stack.enter_async_context(stdio_client(params)),
                    timeout=connect_timeout,
                )
            elif cfg.url:
                from mcp.client.streamable_http import streamable_http_client

                http_client = await server_stack.enter_async_context(
                    httpx.AsyncClient(
                        headers=cfg.headers or None,
                        follow_redirects=True,
                        timeout=None,
                    )
                )
                read, write, _ = await asyncio.wait_for(
                    server_stack.enter_async_context(
                        streamable_http_client(cfg.url, http_client=http_client)
                    ),
                    timeout=connect_timeout,
                )
            else:
                logger.warning(
                    "⚠️ MCP 配置缺失 / config missing: {} has no command/url, skipping",
                    name,
                )
                await server_stack.aclose()
                continue

            session = await server_stack.enter_async_context(ClientSession(read, write))
            await asyncio.wait_for(session.initialize(), timeout=connect_timeout)

            tools = await asyncio.wait_for(session.list_tools(), timeout=connect_timeout)
            connected_servers += 1
            server_count = 0
            pending_names: set[str] = set()
            pending_wrappers: list[MCPToolWrapper] = []
            for tool_def in tools.tools:
                if _reached_global_cap(total_registered, len(pending_wrappers), max_tools):
                    logger.debug(
                        "🔌 MCP 达到上限 / limit reached: ({}) while registering {}",
                        max_tools,
                        name,
                    )
                    break
                if _reached_server_cap(
                    server_count,
                    len(pending_wrappers),
                    server_max_tools,
                ):
                    logger.debug(
                        "🔌 MCP 服务器达到上限 / server limit reached: {} ({} tools)",
                        name,
                        server_max_tools,
                    )
                    break

                server_part = _normalize_name_fragment(name, "server")
                tool_part = _normalize_name_fragment(str(tool_def.name), "tool")
                base_name = f"mcp_{server_part}_{tool_part}"[:64]
                wrapper_name = base_name
                collision_index = 1
                while wrapper_name in pending_names or registry.has(wrapper_name):
                    suffix = f"_{collision_index}"
                    wrapper_name = f"{base_name[: max(1, 64 - len(suffix))]}{suffix}"
                    collision_index += 1
                pending_names.add(wrapper_name)

                wrapper = MCPToolWrapper(
                    session,
                    name,
                    tool_def,
                    timeout=tool_timeout,
                    slim_schema=server_slim_schema,
                    name_override=wrapper_name,
                )
                pending_wrappers.append(wrapper)

            registered_names: list[str] = []
            try:
                for wrapper in pending_wrappers:
                    if _reached_global_cap(total_registered, 0, max_tools):
                        break
                    if _reached_server_cap(server_count, 0, server_max_tools):
                        break
                    registry.register(wrapper)
                    registered_names.append(wrapper.name)
                    total_registered += 1
                    server_count += 1
                    logger.debug("MCP: registered tool '{}' from server '{}'", wrapper.name, name)
            except Exception:
                for tool_name in registered_names:
                    registry.unregister(tool_name)
                raise

            if server_count > 0:
                await stack.enter_async_context(server_stack)
                logger.info("🔌 MCP 已连接 / connected: {} ({} tools)", name, server_count)
            else:
                await server_stack.aclose()
                logger.debug(
                    "MCP connected but no tools registered for server '{}': cap or empty list", name
                )
        except asyncio.CancelledError:
            try:
                await server_stack.aclose()
            except Exception:
                pass
            raise
        except Exception as e:
            logger.error("❌ MCP 连接失败 / connect failed: {} — {}", name, e)
            try:
                await server_stack.aclose()
            except Exception:
                pass

    return total_registered, connected_servers
