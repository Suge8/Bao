from __future__ import annotations

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
