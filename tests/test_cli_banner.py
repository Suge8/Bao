from __future__ import annotations

import io
from contextlib import redirect_stdout

from rich.console import Console

from bao import __logo__, __version__
from bao.cli import commands


def test_print_startup_screen_includes_core_facts(monkeypatch) -> None:
    capture = Console(record=True, width=80, force_terminal=False, color_system=None)
    monkeypatch.setattr(commands, "console", capture)

    model = commands._build_startup_screen_model(
        commands.StartupScreenBuildOptions(
            port=19999,
            enabled_channels=["telegram", "discord"],
            cron_jobs=2,
            heartbeat_interval_s=1800,
            search_providers=["tavily"],
            desktop_enabled=True,
            skills_count=17,
        )
    )
    commands._print_startup_screen(model)

    output = capture.export_text()
    assert __logo__ in output
    assert f"v{__version__}" in output
    assert "port 19999" in output
    assert "BAO 中枢" in output
    assert "记忆驱动的个人 AI 助手中枢" in output
    assert "搜索 SEARCH" in output
    assert "桌面 DESKTOP" in output
    assert "技能 SKILLS" in output
    assert "TAVILY" in output
    assert "READY" in output
    assert "17" in output
    assert "通道 CHANNELS" in output
    assert "定时 CRON" in output
    assert "心跳 HEARTBEAT" in output
    assert "2 在线" in output
    assert "2 项" in output
    assert "30M" in output


def test_build_startup_banner_overlay_probe_does_not_write_to_stdout(monkeypatch) -> None:
    model = commands._build_startup_screen_model(
        commands.StartupScreenBuildOptions(
            port=18790,
            enabled_channels=["imessage"],
            cron_jobs=1,
            heartbeat_interval_s=1800,
            search_providers=["tavily"],
            desktop_enabled=True,
            skills_count=26,
        )
    )
    monkeypatch.setattr(commands, "_detect_terminal_image_protocol", lambda: "kitty")

    stdout = io.StringIO()
    with redirect_stdout(stdout):
        banner = commands._build_startup_banner(model, width=120)

    assert stdout.getvalue() == ""
    assert banner.overlay is not None


def test_detect_terminal_image_protocol_respects_ascii_override(monkeypatch) -> None:
    monkeypatch.setenv("BAO_BANNER_IMAGE", "ascii")
    monkeypatch.setenv("TERM_PROGRAM", "ghostty")
    monkeypatch.setattr(commands, "console", Console(force_terminal=True))

    assert commands._detect_terminal_image_protocol() is None
