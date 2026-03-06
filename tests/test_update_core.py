from __future__ import annotations

from app.backend.update_core import detect_platform_key, resolve_available_release, version_is_newer


def test_detect_platform_key() -> None:
    assert detect_platform_key("darwin", "arm64") == "macos-arm64"
    assert detect_platform_key("darwin", "x86_64") == "macos-x86_64"
    assert detect_platform_key("win32", "AMD64") == "windows-x64"
    assert detect_platform_key("linux", "x86_64") is None


def test_version_is_newer() -> None:
    assert version_is_newer("0.3.8", "0.3.7") is True
    assert version_is_newer("0.3.7", "0.3.7") is False
    assert version_is_newer("0.3.7-beta1", "0.3.7") is False


def test_resolve_available_release_returns_platform_asset() -> None:
    feed = {
        "channels": {
            "stable": {
                "version": "0.3.8",
                "releaseUrl": "https://example.com/release",
                "notesUrl": "https://example.com/notes",
                "notesMarkdown": "- hello",
                "publishedAt": "2026-03-06T00:00:00Z",
                "platforms": {
                    "macos-arm64": {
                        "url": "https://example.com/Bao-0.3.8-macos-arm64-update.zip",
                        "kind": "app-zip",
                        "sha256": "a" * 64,
                        "size": 123,
                    }
                },
            }
        }
    }

    release = resolve_available_release(
        feed,
        channel="stable",
        current_version="0.3.7",
        platform_key="macos-arm64",
    )

    assert release is not None
    assert release.version == "0.3.8"
    assert release.asset.kind == "app-zip"
    assert release.asset.platform == "macos-arm64"


def test_resolve_available_release_returns_none_when_current_is_latest() -> None:
    feed = {
        "channels": {
            "stable": {
                "version": "0.3.7",
                "platforms": {
                    "windows-x64": {
                        "url": "https://example.com/Bao-0.3.7-windows-x64-setup.exe",
                        "kind": "installer-exe",
                        "sha256": "b" * 64,
                        "size": 456,
                    }
                },
            }
        }
    }

    release = resolve_available_release(
        feed,
        channel="stable",
        current_version="0.3.7",
        platform_key="windows-x64",
    )

    assert release is None
