from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

from bao.agent.tool_result import ToolTextResult, cleanup_result_file
from bao.agent.tools._mcp_wrapper_models import (
    MCPToolWrapperSpec,
    RegisterPendingWrappersRequest,
)
from bao.agent.tools.mcp import MCPToolWrapper, _register_pending_wrappers
from bao.agent.tools.registry import ToolRegistry
from bao.config.schema import Config
from tests._mcp_schema_testkit import make_loop


@pytest.mark.asyncio
async def test_agentloop_passes_mcp_slim_and_max_tools(monkeypatch: Any, tmp_path) -> None:
    captured: dict[str, Any] = {}

    async def fake_connect(*args: Any, **kwargs: Any):
        captured.update(
            {
                "mcp_servers": args[0],
                "max_tools": kwargs.get("max_tools", 50),
                "slim_schema": kwargs.get("slim_schema", True),
            }
        )
        return 1, 1

    monkeypatch.setattr("bao.agent.tools.mcp.connect_mcp_servers", fake_connect)
    config = Config()
    config.tools.mcp_max_tools = 7
    config.tools.mcp_slim_schema = False
    loop = make_loop(tmp_path, config=config, mcp_servers={"demo": SimpleNamespace(command="demo")})
    await loop._connect_mcp()
    assert captured["mcp_servers"] and captured["max_tools"] == 7 and captured["slim_schema"] is False
    if loop._mcp_stack:
        await loop._mcp_stack.aclose()


@pytest.mark.asyncio
async def test_wrapper_large_text_and_cancellation(monkeypatch: Any) -> None:
    class _FakeTextContent:
        def __init__(self, text: str) -> None:
            self.text = text

    class _FakeSession:
        async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
            del name, arguments
            return SimpleNamespace(content=[_FakeTextContent("x" * 20000)])

    fake_types = SimpleNamespace(TextContent=_FakeTextContent)
    monkeypatch.setitem(__import__("sys").modules, "mcp", SimpleNamespace(types=fake_types))
    wrapper = MCPToolWrapper(
        _FakeSession(),
        MCPToolWrapperSpec(
            server_name="svc",
            tool_def=SimpleNamespace(name="big", description="big", inputSchema={"type": "object"}),
            slim_schema=True,
        ),
    )
    result = await wrapper.execute()
    assert isinstance(result, ToolTextResult)
    assert "xxx" in result.excerpt
    cleanup_result_file(result)

    async def raise_cancelled(*_args: Any, **_kwargs: Any) -> Any:
        raise asyncio.CancelledError()

    wrapper = MCPToolWrapper(
        SimpleNamespace(call_tool=raise_cancelled),
        MCPToolWrapperSpec(
            server_name="svc",
            tool_def=SimpleNamespace(name="demo", description="Demo tool", inputSchema={"type": "object", "properties": {}}),
            timeout=1,
            slim_schema=True,
        ),
    )
    assert "was cancelled" in await wrapper.execute()


@pytest.mark.asyncio
async def test_mcp_wrapper_reraises_external_task_cancellation(monkeypatch: Any) -> None:
    import sys
    import types

    fake_mcp = types.ModuleType("mcp")
    fake_mcp.types = SimpleNamespace(TextContent=type("TextContent", (), {}))
    monkeypatch.setitem(sys.modules, "mcp", fake_mcp)

    started = asyncio.Event()

    async def wait_forever(*_args: Any, **_kwargs: Any) -> Any:
        started.set()
        await asyncio.Future()

    wrapper = MCPToolWrapper(
        SimpleNamespace(call_tool=wait_forever),
        MCPToolWrapperSpec(
            server_name="svc",
            tool_def=SimpleNamespace(name="demo", description="Demo tool", inputSchema={"type": "object", "properties": {}}),
            timeout=5,
            slim_schema=True,
        ),
    )
    task = asyncio.create_task(wrapper.execute())
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


def test_register_pending_wrappers_populates_discoverability_metadata() -> None:
    registry = ToolRegistry()
    wrapper = MCPToolWrapper(
        object(),
        MCPToolWrapperSpec(
            server_name="crm",
            tool_def=SimpleNamespace(
                name="lookup",
                description="Look up a customer record",
                inputSchema={"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]},
            ),
            slim_schema=True,
        ),
    )
    server_count, total_registered = _register_pending_wrappers(
        RegisterPendingWrappersRequest(
            pending_wrappers=[wrapper],
            registry=registry,
            total_registered=0,
            max_tools=50,
            server_max_tools=None,
            server_name="crm",
        )
    )
    meta = registry.get_metadata(wrapper.name)
    assert server_count == 1 and total_registered == 1
    assert meta is not None and meta.bundle == "core"
    assert "lookup" in meta.aliases and "crm" not in meta.aliases


@pytest.mark.asyncio
async def test_mcp_connection_state_flags(monkeypatch: Any, tmp_path) -> None:
    async def fake_connect_zero(*args, **kwargs) -> tuple[int, int]:
        del args, kwargs
        return 0, 0

    monkeypatch.setattr("bao.agent.tools.mcp.connect_mcp_servers", fake_connect_zero)
    loop = make_loop(tmp_path, config=Config(), mcp_servers={"demo": SimpleNamespace(command="demo")})
    await loop._connect_mcp()
    assert loop._mcp_connected is False and loop._mcp_connect_succeeded is False
    config = Config()
    config.tools.mcp_max_tools = True  # type: ignore[assignment]
    assert make_loop(tmp_path, config=config)._mcp_max_tools == 50
    config = Config()
    config.tools.mcp_max_tools = -3
    assert make_loop(tmp_path, config=config)._mcp_max_tools == 0

    async def fake_connect_ok(*args, **kwargs) -> tuple[int, int]:
        del args, kwargs
        return 2, 1

    monkeypatch.setattr("bao.agent.tools.mcp.connect_mcp_servers", fake_connect_ok)
    loop = make_loop(tmp_path, config=Config(), mcp_servers={"demo": SimpleNamespace(command="demo")})
    await loop._connect_mcp()
    assert loop._mcp_connected is True and loop._mcp_connect_succeeded is True
    if loop._mcp_stack:
        await loop._mcp_stack.aclose()


@pytest.mark.asyncio
async def test_mcp_no_tools_retries_on_next_connect_attempt(monkeypatch: Any, tmp_path) -> None:
    calls = {"count": 0}

    async def fake_connect_no_tools(*args, **kwargs) -> tuple[int, int]:
        del args, kwargs
        calls["count"] += 1
        return 0, 1

    monkeypatch.setattr("bao.agent.tools.mcp.connect_mcp_servers", fake_connect_no_tools)
    loop = make_loop(tmp_path, config=Config(), mcp_servers={"demo": SimpleNamespace(command="demo")})
    await loop._connect_mcp()
    await loop._connect_mcp()
    assert calls["count"] == 2
    assert loop._mcp_connected is False and loop._mcp_connect_succeeded is True and loop._mcp_stack is None
