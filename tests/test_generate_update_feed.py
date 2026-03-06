from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from app.scripts.generate_update_feed import build_feed


def test_build_feed_generates_platform_payloads(tmp_path: Path) -> None:
    release_json = tmp_path / "release.json"
    release_json.write_text(
        json.dumps(
            {
                "tagName": "v0.3.8",
                "url": "https://github.com/Suge8/Bao/releases/tag/v0.3.8",
                "publishedAt": "2026-03-06T00:00:00Z",
                "body": "- shipped",
            }
        ),
        encoding="utf-8",
    )

    assets_dir = tmp_path / "assets"
    assets_dir.mkdir()
    mac_asset = assets_dir / "Bao-0.3.8-macos-arm64-update.zip"
    win_asset = assets_dir / "Bao-0.3.8-windows-x64-setup.exe"
    mac_asset.write_bytes(b"mac-update")
    win_asset.write_bytes(b"win-update")

    feed = build_feed(
        release_json=release_json,
        assets_dir=assets_dir,
        repo="Suge8/Bao",
        channel="stable",
    )

    channels = cast(dict[str, object], feed["channels"])
    stable = cast(dict[str, object], channels["stable"])
    platforms = cast(dict[str, object], stable["platforms"])
    windows = cast(dict[str, object], platforms["windows-x64"])
    macos = cast(dict[str, object], platforms["macos-arm64"])

    assert stable["version"] == "0.3.8"
    assert macos["kind"] == "app-zip"
    assert windows["kind"] == "installer-exe"
    assert windows["silentArgs"] == [
        "/VERYSILENT",
        "/SUPPRESSMSGBOXES",
        "/NORESTART",
        "/SP-",
    ]
