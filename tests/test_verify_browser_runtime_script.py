from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from bao.browser import BrowserCapabilityState

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _load_verify_script_module():
    spec = importlib.util.spec_from_file_location(
        "verify_browser_runtime_script",
        PROJECT_ROOT / "app/scripts/verify_browser_runtime.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _ready_state(runtime_root: Path) -> BrowserCapabilityState:
    return BrowserCapabilityState(
        enabled=True,
        available=True,
        runtime_ready=True,
        runtime_root=str(runtime_root),
        runtime_source="env",
        profile_path=str(runtime_root / "profile"),
        agent_browser_home_path=str(runtime_root / "node_modules" / "agent-browser"),
        agent_browser_path=str(runtime_root / "platforms" / "darwin-arm64" / "bin" / "agent-browser"),
        browser_executable_path=str(
            runtime_root
            / "platforms"
            / "darwin-arm64"
            / "browser"
            / "chrome"
            / "Google Chrome for Testing.app"
            / "Contents"
            / "MacOS"
            / "Google Chrome for Testing"
        ),
        reason="ready",
        detail="Managed browser runtime is ready.",
    )


def test_verify_browser_runtime_ready_check_skips_smoke_by_default(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    script = _load_verify_script_module()
    state = _ready_state(tmp_path / "runtime")

    class UnexpectedService:
        def __init__(self, *args, **kwargs) -> None:
            raise AssertionError("smoke service should not be created without --smoke")

    monkeypatch.setattr("bao.browser.get_browser_capability_state", lambda *, enabled=True: state)
    monkeypatch.setattr("bao.browser.BrowserAutomationService", UnexpectedService)
    monkeypatch.setattr(sys, "argv", ["verify_browser_runtime.py", "--require-ready"])

    assert script.main() == 0
    output = capsys.readouterr().out
    assert "Managed browser runtime ready" in output
    assert "smoke:" not in output


def test_verify_browser_runtime_runs_smoke_when_requested(monkeypatch, tmp_path: Path, capsys) -> None:
    script = _load_verify_script_module()
    state = _ready_state(tmp_path / "runtime")

    class FakeService:
        def __init__(self, *, workspace: Path) -> None:
            assert workspace == PROJECT_ROOT

        async def smoke_test(self) -> str | None:
            return None

    monkeypatch.setattr("bao.browser.get_browser_capability_state", lambda *, enabled=True: state)
    monkeypatch.setattr("bao.browser.BrowserAutomationService", FakeService)
    monkeypatch.setattr(sys, "argv", ["verify_browser_runtime.py", "--require-ready", "--smoke"])

    assert script.main() == 0
    output = capsys.readouterr().out
    assert "Managed browser runtime ready" in output
    assert "smoke:              passed" in output
