from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from bao.cli.commands import app, run_hub
from bao.config.loader import load_config
from bao.config.paths import (
    get_bridge_install_dir,
    get_cli_history_path,
    get_config_path,
    get_data_dir,
    get_media_dir,
    get_runtime_subdir,
    set_runtime_config_path,
)


def test_load_config_with_custom_path_switches_runtime_dirs(tmp_path: Path) -> None:
    cfg = tmp_path / "instance" / "config.jsonc"
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text("{}", encoding="utf-8")

    set_runtime_config_path(None)
    load_config(cfg)

    assert get_config_path() == cfg
    assert get_data_dir() == cfg.parent
    assert get_media_dir() == cfg.parent / "media"
    assert get_runtime_subdir("cron") == cfg.parent / "cron"
    assert get_cli_history_path() == cfg.parent / "history" / "cli_history"
    assert get_bridge_install_dir() == cfg.parent / "bridge"

    set_runtime_config_path(None)


def test_default_runtime_dirs_follow_home(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    set_runtime_config_path(None)

    assert get_data_dir() == tmp_path / ".bao"
    assert get_media_dir() == tmp_path / ".bao" / "media"


def test_cli_default_invocation_runs_gateway(monkeypatch) -> None:
    captured: list[object] = []

    monkeypatch.setattr("bao.cli.commands.run_hub", lambda *, options=None, **kwargs: captured.append(options))

    result = CliRunner().invoke(app, [])

    assert result.exit_code == 0
    assert captured
    options = captured[0]
    assert options is not None
    assert options.port is None
    assert options.workspace is None
    assert options.config_path is None
    assert options.verbose is False
    assert "Bao v" not in result.stdout


def test_run_gateway_uses_config_port_when_cli_omits(monkeypatch) -> None:
    config = MagicMock()
    config.hub.port = 19999
    config.workspace_path = Path("/tmp/workspace")

    fake_stack = SimpleNamespace(
        channels=SimpleNamespace(enabled_channels=[]),
        cron=SimpleNamespace(status=lambda: {"jobs": 0}, start=MagicMock(), stop=MagicMock()),
        heartbeat=SimpleNamespace(interval_s=1800, start=MagicMock(), stop=MagicMock()),
        agent=SimpleNamespace(run=MagicMock(), close_mcp=MagicMock(), stop=MagicMock()),
        bus=MagicMock(),
        config=config,
        session_manager=MagicMock(),
    )
    fake_stack.channels.start_all = MagicMock()
    fake_stack.channels.stop_all = MagicMock()

    startup_ports: list[int] = []

    monkeypatch.setattr("bao.cli.commands._setup_logging", lambda verbose: None)
    monkeypatch.setattr("bao.cli.commands._make_provider", lambda cfg: object())
    monkeypatch.setattr(
        "bao.cli.commands._print_startup_screen", lambda model: startup_ports.append(model.port)
    )
    monkeypatch.setattr("bao.cli.commands.asyncio.run", lambda coro: coro.close())

    with (
        patch("bao.config.loader.load_config", return_value=config),
        patch("bao.hub.builder.build_hub_stack", return_value=fake_stack),
        patch("bao.hub.builder.send_startup_greeting", return_value=MagicMock()),
    ):
        run_hub(port=None, verbose=False)

    assert startup_ports == [19999]


def test_run_gateway_workspace_override_wins(monkeypatch) -> None:
    config = MagicMock()
    config.hub.port = 18790
    config.agents.defaults.workspace = "~/.bao/workspace"
    config.workspace_path = Path("/tmp/original")

    fake_stack = SimpleNamespace(
        channels=SimpleNamespace(enabled_channels=[]),
        cron=SimpleNamespace(status=lambda: {"jobs": 0}, start=MagicMock(), stop=MagicMock()),
        heartbeat=SimpleNamespace(interval_s=1800, start=MagicMock(), stop=MagicMock()),
        agent=SimpleNamespace(run=MagicMock(), close_mcp=MagicMock(), stop=MagicMock()),
        bus=MagicMock(),
        config=config,
        session_manager=MagicMock(),
    )
    fake_stack.channels.start_all = MagicMock()
    fake_stack.channels.stop_all = MagicMock()

    monkeypatch.setattr("bao.cli.commands._setup_logging", lambda verbose: None)
    monkeypatch.setattr("bao.cli.commands._make_provider", lambda cfg: object())
    monkeypatch.setattr("bao.cli.commands._print_startup_screen", lambda model: None)
    monkeypatch.setattr("bao.cli.commands.asyncio.run", lambda coro: coro.close())

    with (
        patch("bao.config.loader.load_config", return_value=config),
        patch("bao.hub.builder.build_hub_stack", return_value=fake_stack),
        patch("bao.hub.builder.send_startup_greeting", return_value=MagicMock()),
    ):
        run_hub(port=12345, verbose=False, workspace="~/custom-workspace")

    assert config.agents.defaults.workspace == "~/custom-workspace"
