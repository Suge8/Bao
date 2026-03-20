from __future__ import annotations

import asyncio
from contextlib import AsyncExitStack
from typing import Any

import httpx

from bao.agent.tools._mcp_common import resolve_transport_type


async def close_stack_quietly(stack: AsyncExitStack) -> None:
    try:
        await stack.aclose()
    except Exception:
        pass


async def open_server_streams(cfg: Any, server_stack: AsyncExitStack, connect_timeout: int):
    transport_type = resolve_transport_type(cfg)
    if transport_type == "stdio":
        from mcp import StdioServerParameters
        from mcp.client.stdio import stdio_client

        params = StdioServerParameters(command=cfg.command, args=cfg.args, env=cfg.env or None)
        return await asyncio.wait_for(
            server_stack.enter_async_context(stdio_client(params)),
            timeout=connect_timeout,
        )

    if transport_type == "sse":
        from mcp.client.sse import sse_client

        def httpx_client_factory(
            headers: dict[str, str] | None = None,
            timeout: httpx.Timeout | None = None,
            auth: httpx.Auth | None = None,
        ) -> httpx.AsyncClient:
            merged_headers = {**(cfg.headers or {}), **(headers or {})}
            return httpx.AsyncClient(
                headers=merged_headers or None,
                follow_redirects=True,
                timeout=timeout,
                auth=auth,
            )

        return await asyncio.wait_for(
            server_stack.enter_async_context(
                sse_client(cfg.url, httpx_client_factory=httpx_client_factory)
            ),
            timeout=connect_timeout,
        )

    if transport_type == "streamableHttp":
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
        return read, write

    return None
