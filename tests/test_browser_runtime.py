from __future__ import annotations

import json
from pathlib import Path

from bao.browser import (
    BrowserAutomationService,
    current_browser_platform_key,
    get_browser_capability_state,
)
from bao.config.paths import set_runtime_config_path
from tests.browser_runtime_fixture import write_fake_browser_runtime


def test_browser_capability_state_uses_env_runtime_root(tmp_path: Path, monkeypatch) -> None:
    runtime_root = write_fake_browser_runtime(tmp_path)
    platform_key = current_browser_platform_key()
    agent_binary = "agent-browser.exe" if platform_key.startswith("win32-") else "agent-browser"
    browser_binary = "chrome.exe" if platform_key.startswith("win32-") else "chrome"
    monkeypatch.setenv("BAO_BROWSER_RUNTIME_ROOT", str(runtime_root))
    set_runtime_config_path(tmp_path / "config.jsonc")
    try:
        state = get_browser_capability_state(enabled=True)
    finally:
        set_runtime_config_path(None)

    assert state.available is True
    assert state.runtime_ready is True
    assert state.runtime_source == "env"
    assert state.runtime_root == str(runtime_root)
    assert state.agent_browser_path == str(
        runtime_root / "platforms" / platform_key / "bin" / agent_binary
    )
    assert state.browser_executable_path == str(
        runtime_root / "platforms" / platform_key / "browser" / browser_binary
    )
    assert state.profile_path == str((tmp_path / "browser" / "profile").resolve(strict=False))


def test_browser_capability_state_reports_missing_browser_binary(
    tmp_path: Path, monkeypatch
) -> None:
    runtime_root = tmp_path / "runtime"
    platform_key = current_browser_platform_key()
    binary_name = "agent-browser.exe" if platform_key.startswith("win32-") else "agent-browser"
    (runtime_root / "platforms" / platform_key / "bin").mkdir(parents=True, exist_ok=True)
    (runtime_root / "runtime.json").write_text(
        json.dumps(
            {
                "source": "agent-browser",
                "version": "0.19.0",
                "platforms": {
                    platform_key: {
                        "agentBrowserPath": f"platforms/{platform_key}/bin/{binary_name}"
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("BAO_BROWSER_RUNTIME_ROOT", str(runtime_root))
    set_runtime_config_path(tmp_path / "config.jsonc")
    try:
        state = get_browser_capability_state(enabled=True)
    finally:
        set_runtime_config_path(None)

    assert state.available is False
    assert state.reason == "agent_browser_missing"


def test_browser_automation_service_can_be_disabled(tmp_path: Path) -> None:
    set_runtime_config_path(tmp_path / "config.jsonc")
    try:
        service = BrowserAutomationService(workspace=tmp_path, enabled=False)
        state = service.state
    finally:
        set_runtime_config_path(None)

    assert state.enabled is False
    assert state.reason == "disabled"
    assert service.available is False


def test_browser_capability_state_reports_missing_current_platform_entry(
    tmp_path: Path, monkeypatch
) -> None:
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir(parents=True, exist_ok=True)
    current_platform = current_browser_platform_key()
    other_platform = "win32-x64" if current_platform != "win32-x64" else "darwin-arm64"
    (runtime_root / "runtime.json").write_text(
        json.dumps(
            {
                "source": "agent-browser",
                "version": "0.19.0",
                "platforms": {
                    other_platform: {
                        "agentBrowserPath": f"platforms/{other_platform}/bin/agent-browser",
                        "browserExecutablePath": f"platforms/{other_platform}/browser/chrome",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("BAO_BROWSER_RUNTIME_ROOT", str(runtime_root))
    set_runtime_config_path(tmp_path / "config.jsonc")
    try:
        state = get_browser_capability_state(enabled=True)
    finally:
        set_runtime_config_path(None)

    assert state.available is False
    assert state.reason == "platform_missing"
