from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


MAC_PATTERN = re.compile(r"^Bao-(?P<version>[^/]+)-macos-(?P<arch>arm64|x86_64)-update\.zip$")
WIN_PATTERN = re.compile(r"^Bao-(?P<version>[^/]+)-windows-x64-setup\.exe$")


def build_feed(
    *, release_json: Path, assets_dir: Path, repo: str, channel: str
) -> dict[str, object]:
    release = json.loads(release_json.read_text(encoding="utf-8"))
    tag = _read_str(release, "tagName") or _read_str(release, "tag_name")
    version = tag.removeprefix("v")
    if not tag or not version:
        raise ValueError("Release JSON is missing tagName")

    asset_map: dict[str, dict[str, object]] = {}
    for file_path in sorted(assets_dir.iterdir()):
        if not file_path.is_file():
            continue
        mac_match = MAC_PATTERN.match(file_path.name)
        if mac_match:
            asset_map[f"macos-{mac_match.group('arch')}"] = _asset_payload(
                file_path=file_path,
                url=_download_url(repo, tag, file_path.name),
                kind="app-zip",
            )
            continue
        if WIN_PATTERN.match(file_path.name):
            payload = _asset_payload(
                file_path=file_path,
                url=_download_url(repo, tag, file_path.name),
                kind="installer-exe",
            )
            payload["silentArgs"] = ["/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-"]
            asset_map["windows-x64"] = payload

    if not asset_map:
        raise ValueError(f"No update assets found in {assets_dir}")

    return {
        "app": "bao-desktop",
        "generatedAt": _read_str(release, "publishedAt") or _read_str(release, "published_at"),
        "channels": {
            channel: {
                "version": version,
                "releaseUrl": _read_str(release, "url") or _read_str(release, "html_url"),
                "notesUrl": _read_str(release, "url") or _read_str(release, "html_url"),
                "notesMarkdown": _read_str(release, "body"),
                "publishedAt": _read_str(release, "publishedAt")
                or _read_str(release, "published_at"),
                "platforms": asset_map,
            }
        },
    }


def _asset_payload(*, file_path: Path, url: str, kind: str) -> dict[str, object]:
    return {
        "url": url,
        "kind": kind,
        "size": file_path.stat().st_size,
        "sha256": _sha256(file_path),
    }


def _sha256(file_path: Path) -> str:
    digest = hashlib.sha256()
    with file_path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download_url(repo: str, tag: str, file_name: str) -> str:
    return f"https://github.com/{repo}/releases/download/{tag}/{file_name}"


def _read_str(data: dict[str, object], key: str) -> str:
    value = data.get(key)
    return value if isinstance(value, str) else ""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release-json", required=True)
    parser.add_argument("--assets-dir", required=True)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--channel", default="stable")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    feed = build_feed(
        release_json=Path(args.release_json),
        assets_dir=Path(args.assets_dir),
        repo=args.repo,
        channel=args.channel,
    )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(feed, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
