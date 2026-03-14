from __future__ import annotations

import json
from pathlib import Path

from app.scripts import update_agent_browser_runtime as runtime_script


def test_npm_command_uses_cmd_on_windows(monkeypatch) -> None:
    monkeypatch.setattr(runtime_script.sys, "platform", "win32")

    assert runtime_script._npm_command() == ["npm.cmd"]


def test_npm_command_uses_npm_on_unix(monkeypatch) -> None:
    monkeypatch.setattr(runtime_script.sys, "platform", "darwin")

    assert runtime_script._npm_command() == ["npm"]


def test_sync_browser_bundle_from_cache_prefers_new_entries(tmp_path: Path) -> None:
    cache_root = tmp_path / "cache"
    browser_dir = tmp_path / "runtime" / "browser"
    old_dir = cache_root / "old-browser"
    new_dir = cache_root / "chrome-146.0.7680.80"
    old_dir.mkdir(parents=True, exist_ok=True)
    new_dir.mkdir(parents=True, exist_ok=True)
    (old_dir / "stale.txt").write_text("old", encoding="utf-8")
    (new_dir / "chrome-linux" / "chrome").parent.mkdir(parents=True, exist_ok=True)
    (new_dir / "chrome-linux" / "chrome").write_text("", encoding="utf-8")
    browser_dir.mkdir(parents=True, exist_ok=True)

    runtime_script._sync_browser_bundle_from_cache(
        cache_root=cache_root,
        browser_dir=browser_dir,
        before_snapshot={"old-browser"},
    )

    assert (browser_dir / "chrome-146.0.7680.80" / "chrome-linux" / "chrome").is_file()
    assert not (browser_dir / "old-browser").exists()


def test_detect_browser_executable_supports_windows_win64_layout(tmp_path: Path) -> None:
    browser_dir = tmp_path / "browser"
    executable = browser_dir / "chrome-146.0.7680.80" / "chrome-win64" / "chrome.exe"
    executable.parent.mkdir(parents=True, exist_ok=True)
    executable.write_text("", encoding="utf-8")

    detected = runtime_script.detect_browser_executable(
        browser_dir=browser_dir,
        platform_key="win32-x64",
    )

    assert detected == executable


def test_vendor_agent_browser_home_copies_node_modules_tree(tmp_path: Path, monkeypatch) -> None:
    install_dir = tmp_path / "install"
    source_home = install_dir / "node_modules" / "agent-browser"
    (source_home / "bin").mkdir(parents=True, exist_ok=True)
    (source_home / "package.json").write_text('{"name":"agent-browser"}\n', encoding="utf-8")
    (source_home / "bin" / "agent-browser.js").write_text("#!/usr/bin/env node\n", encoding="utf-8")
    (install_dir / "node_modules" / "ws" / "index.js").parent.mkdir(parents=True, exist_ok=True)
    (install_dir / "node_modules" / "ws" / "index.js").write_text("", encoding="utf-8")
    monkeypatch.setattr(runtime_script, "RUNTIME_ROOT", tmp_path / "runtime")

    agent_browser_home = runtime_script.vendor_agent_browser_home(install_dir=install_dir)

    assert agent_browser_home == tmp_path / "runtime" / "node_modules" / "agent-browser"
    assert (agent_browser_home / "bin" / "agent-browser.js").is_file()
    assert (tmp_path / "runtime" / "node_modules" / "ws" / "index.js").is_file()


def test_update_runtime_manifest_records_agent_browser_home(tmp_path: Path, monkeypatch) -> None:
    runtime_root = tmp_path / "runtime"
    monkeypatch.setattr(runtime_script, "RUNTIME_ROOT", runtime_root)
    browser_dir = runtime_root / "platforms" / "darwin-arm64" / "browser"
    executable = (
        browser_dir
        / "chromium-1208"
        / "chrome-mac-arm64"
        / "Google Chrome for Testing.app"
        / "Contents"
        / "MacOS"
        / "Google Chrome for Testing"
    )
    executable.parent.mkdir(parents=True, exist_ok=True)
    executable.write_text("", encoding="utf-8")
    agent_browser_home = runtime_root / "node_modules" / "agent-browser"
    agent_browser_home.mkdir(parents=True, exist_ok=True)

    runtime_script.update_runtime_manifest(
        version="0.19.0",
        platform_key="darwin-arm64",
        browser_dir=browser_dir,
        agent_browser_home=agent_browser_home,
    )

    manifest = json.loads((runtime_root / "runtime.json").read_text(encoding="utf-8"))
    assert manifest["platforms"]["darwin-arm64"]["agentBrowserHomePath"] == "node_modules/agent-browser"
