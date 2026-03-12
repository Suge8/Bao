from __future__ import annotations

import importlib
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import cast
from unittest.mock import patch

from app.backend.asyncio_runner import AsyncioRunner

pytest = importlib.import_module("pytest")
pytestmark = [pytest.mark.integration, pytest.mark.gui]

QtCore = pytest.importorskip("PySide6.QtCore")
QCoreApplication = QtCore.QCoreApplication

MINIMAL_CONFIG = """{
  "providers": {
    "openaiCompatible": {
      "apiKey": "sk-test",
      "baseUrl": "https://api.openai.com/v1"
    }
  },
  "agents": {
    "defaults": {
      "model": "openai/gpt-4o"
    }
  },
  "tools": {
    "mcpServers": {}
  }
}"""


@pytest.fixture(scope="module", autouse=True)
def qt_app():
    app = QCoreApplication.instance() or QCoreApplication(sys.argv)
    yield app


@pytest.fixture()
def runner() -> Iterator[AsyncioRunner]:
    current = AsyncioRunner()
    current.start()
    try:
        yield current
    finally:
        current.shutdown()


@pytest.fixture()
def config_service(tmp_path: Path):
    from app.backend.config import ConfigService

    cfg = tmp_path / "config.jsonc"
    cfg.write_text(MINIMAL_CONFIG, encoding="utf-8")
    service = ConfigService()
    with patch("bao.config.loader.get_config_path", return_value=cfg):
        service.load()
    return service


def test_tools_service_normalizes_and_saves_stdio_server(
    runner: AsyncioRunner, config_service
) -> None:
    from app.backend.tools import ToolsService

    service = ToolsService(runner, config_service)
    events: list[tuple[str, bool]] = []
    _ = service.operationFinished.connect(
        lambda message, ok: events.append((str(message), bool(ok)))
    )

    ok = service.saveMcpServer(
        {
            "name": "figma",
            "transport": "stdio",
            "command": "npx",
            "argsText": "-y\n@modelcontextprotocol/server-figma",
            "envText": "FIGMA_TOKEN=demo",
            "toolTimeoutSeconds": "45",
            "maxTools": "3",
            "slimSchema": True,
        }
    )

    assert ok is True
    assert events[-1] == ("saved", True)
    saved = cast(dict[str, object], config_service.get("tools.mcpServers.figma", {}))
    assert saved["command"] == "npx"
    assert saved["args"] == ["-y", "@modelcontextprotocol/server-figma"]
    assert saved["env"] == {"FIGMA_TOKEN": "demo"}
    assert saved["toolTimeoutSeconds"] == 45
    assert saved["maxTools"] == 3
    assert saved["slimSchema"] is True


def test_tools_service_emits_validation_error_for_invalid_http_server(
    runner: AsyncioRunner, config_service
) -> None:
    from app.backend.tools import ToolsService

    service = ToolsService(runner, config_service)
    events: list[tuple[str, bool]] = []
    _ = service.operationFinished.connect(
        lambda message, ok: events.append((str(message), bool(ok)))
    )

    ok = service.saveMcpServer({"name": "remote", "transport": "http", "url": ""})

    assert ok is False
    assert events[-1] == ("URL is required for HTTP MCP servers.", False)
    assert cast(str, cast(object, service.lastError)) == "URL is required for HTTP MCP servers."


def test_tools_service_delete_mcp_server_updates_config(
    runner: AsyncioRunner, config_service
) -> None:
    from app.backend.tools import ToolsService

    assert (
        config_service.save(
            {
                "tools.mcpServers.demo.command": "uvx",
                "tools.mcpServers.demo.args": ["demo-server"],
            }
        )
        is True
    )
    service = ToolsService(runner, config_service)
    service.setConfigData(config_service.exportData())
    events: list[tuple[str, bool]] = []
    _ = service.operationFinished.connect(
        lambda message, ok: events.append((str(message), bool(ok)))
    )

    assert service.deleteMcpServer("demo") is True
    assert events[-1] == ("deleted", True)
    assert cast(dict[str, object], config_service.get("tools.mcpServers", {})) == {}


def test_tools_service_rejects_duplicate_mcp_server_name(
    runner: AsyncioRunner, config_service
) -> None:
    from app.backend.tools import ToolsService

    assert config_service.save({"tools.mcpServers.demo.command": "uvx"}) is True
    service = ToolsService(runner, config_service)
    events: list[tuple[str, bool]] = []
    _ = service.operationFinished.connect(
        lambda message, ok: events.append((str(message), bool(ok)))
    )

    ok = service.saveMcpServer({"name": "demo", "transport": "stdio", "command": "npx"})

    assert ok is False
    assert events[-1] == ("MCP server already exists: demo", False)


def test_tools_service_preserves_none_slim_schema(runner: AsyncioRunner, config_service) -> None:
    from app.backend.tools import ToolsService

    service = ToolsService(runner, config_service)

    ok = service.saveMcpServer(
        {
            "name": "inherit-demo",
            "transport": "stdio",
            "command": "uvx",
            "slimSchema": None,
        }
    )

    assert ok is True
    saved = cast(dict[str, object], config_service.get("tools.mcpServers.inherit-demo", {}))
    assert saved["slimSchema"] is None
