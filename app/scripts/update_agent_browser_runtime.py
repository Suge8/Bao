from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_ROOT = PROJECT_ROOT / "app" / "resources" / "runtime" / "browser"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

_PACKAGE_BINARY_MAP = {
    "darwin-arm64": ("bin/agent-browser-darwin-arm64", "platforms/darwin-arm64/bin/agent-browser"),
    "darwin-x64": ("bin/agent-browser-darwin-x64", "platforms/darwin-x64/bin/agent-browser"),
    "linux-arm64": ("bin/agent-browser-linux-arm64", "platforms/linux-arm64/bin/agent-browser"),
    "linux-x64": ("bin/agent-browser-linux-x64", "platforms/linux-x64/bin/agent-browser"),
    "win32-x64": (
        "bin/agent-browser-win32-x64.exe",
        "platforms/win32-x64/bin/agent-browser.exe",
    ),
}
_CURRENT_PLATFORM_BROWSER_GLOBS = {
    "darwin-arm64": ("**/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing",),
    "darwin-x64": ("**/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing",),
    "linux-arm64": ("**/chrome-linux/chrome",),
    "linux-x64": ("**/chrome-linux/chrome",),
    "win32-x64": ("**/chrome-win64/chrome.exe", "**/chrome-win/chrome.exe"),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download and vendor the latest official agent-browser runtime."
    )
    parser.add_argument(
        "--version",
        default="latest",
        help="agent-browser version to vendor. Default: latest",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    version = resolve_version(args.version)
    platform_key = _current_platform_key()

    with tempfile.TemporaryDirectory(prefix="bao-agent-browser-") as temp_dir_raw:
        temp_dir = Path(temp_dir_raw)
        extract_dir = temp_dir / "extract"
        install_dir = temp_dir / "install"
        browser_dir = RUNTIME_ROOT / "platforms" / platform_key / "browser"

        tarball = npm_pack(version=version, workdir=temp_dir)
        extract_package(tarball=tarball, extract_dir=extract_dir)
        install_package(version=version, install_dir=install_dir)

        vendor_native_binaries(package_dir=extract_dir / "package")
        vendor_browser_bundle(
            install_dir=install_dir,
            browser_dir=browser_dir,
        )
        update_runtime_manifest(version=version, platform_key=platform_key, browser_dir=browser_dir)

    print(f"[ok] Vendored agent-browser {version} for {platform_key} into {RUNTIME_ROOT}")
    return 0


def resolve_version(version: str) -> str:
    requested = version.strip() or "latest"
    if requested != "latest":
        return requested
    output = subprocess.run(
        [*_npm_command(), "view", "agent-browser", "version"],
        check=True,
        capture_output=True,
        text=True,
    )
    return output.stdout.strip()


def npm_pack(*, version: str, workdir: Path) -> Path:
    output = subprocess.run(
        [*_npm_command(), "pack", f"agent-browser@{version}"],
        check=True,
        cwd=workdir,
        capture_output=True,
        text=True,
    )
    tarball_name = output.stdout.strip().splitlines()[-1]
    return workdir / tarball_name


def extract_package(*, tarball: Path, extract_dir: Path) -> None:
    extract_dir.mkdir(parents=True, exist_ok=True)
    with tarfile.open(tarball, "r:gz") as archive:
        archive.extractall(extract_dir, filter="data")


def install_package(*, version: str, install_dir: Path) -> None:
    install_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [*_npm_command(), "install", "--prefix", str(install_dir), f"agent-browser@{version}"],
        check=True,
    )


def vendor_native_binaries(*, package_dir: Path) -> None:
    for src_rel, dst_rel in _PACKAGE_BINARY_MAP.values():
        src = package_dir / src_rel
        dst = RUNTIME_ROOT / dst_rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        if dst.suffix != ".exe":
            dst.chmod(0o755)


def vendor_browser_bundle(*, install_dir: Path, browser_dir: Path) -> None:
    browser_dir.parent.mkdir(parents=True, exist_ok=True)
    if browser_dir.exists():
        shutil.rmtree(browser_dir)
    browser_dir.mkdir(parents=True, exist_ok=True)

    default_cache_root = _default_agent_browser_cache_root()
    cache_before = _directory_snapshot(default_cache_root)
    env = os.environ.copy()
    env["PLAYWRIGHT_BROWSERS_PATH"] = str(browser_dir)
    subprocess.run(
        _agent_browser_install_command(install_dir),
        check=True,
        cwd=install_dir,
        env=env,
    )
    if any(browser_dir.iterdir()) and _contains_browser_bundle(browser_dir):
        return
    _sync_browser_bundle_from_cache(
        cache_root=default_cache_root,
        browser_dir=browser_dir,
        before_snapshot=cache_before,
    )


def update_runtime_manifest(*, version: str, platform_key: str, browser_dir: Path) -> None:
    manifest_path = RUNTIME_ROOT / "runtime.json"
    manifest = {}
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict):
            manifest = {}

    browser_executable = detect_browser_executable(browser_dir=browser_dir, platform_key=platform_key)
    platforms = manifest.get("platforms")
    if not isinstance(platforms, dict):
        platforms = {}

    agent_browser_rel = _PACKAGE_BINARY_MAP[platform_key][1]
    platforms[platform_key] = {
        "agentBrowserPath": agent_browser_rel,
        "browserExecutablePath": str(browser_executable.relative_to(RUNTIME_ROOT)),
    }

    manifest["source"] = "agent-browser"
    manifest["version"] = version
    manifest["platforms"] = dict(sorted(platforms.items()))
    manifest.pop("agentBrowserPath", None)
    manifest.pop("browserExecutablePath", None)
    RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def detect_browser_executable(*, browser_dir: Path, platform_key: str) -> Path:
    for pattern in _CURRENT_PLATFORM_BROWSER_GLOBS[platform_key]:
        matches = sorted(browser_dir.glob(pattern))
        if matches:
            return matches[0]
    raise RuntimeError(f"Could not locate browser executable under {browser_dir}")


def _current_platform_key() -> str:
    from bao.browser import current_browser_platform_key

    return current_browser_platform_key()


def _npm_command() -> list[str]:
    if sys.platform in {"win32", "cygwin"}:
        return ["npm.cmd"]
    return ["npm"]


def _agent_browser_install_command(install_dir: Path) -> list[str]:
    if sys.platform in {"win32", "cygwin"}:
        cli = install_dir / "node_modules" / ".bin" / "agent-browser.cmd"
        return ["cmd", "/c", str(cli), "install"]
    cli = install_dir / "node_modules" / ".bin" / "agent-browser"
    return [str(cli), "install"]


def _default_agent_browser_cache_root() -> Path:
    return Path.home() / ".agent-browser" / "browsers"


def _directory_snapshot(root: Path) -> set[str]:
    if not root.is_dir():
        return set()
    return {child.name for child in root.iterdir()}


def _sync_browser_bundle_from_cache(
    *,
    cache_root: Path,
    browser_dir: Path,
    before_snapshot: set[str],
) -> None:
    if not cache_root.is_dir():
        return
    child_names = sorted(child.name for child in cache_root.iterdir())
    preferred_names = [name for name in child_names if name not in before_snapshot]
    names_to_copy = preferred_names or child_names
    for name in names_to_copy:
        source = cache_root / name
        target = browser_dir / name
        if target.exists():
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink()
        if source.is_dir():
            shutil.copytree(source, target)
        else:
            shutil.copy2(source, target)


def _contains_browser_bundle(browser_dir: Path) -> bool:
    for patterns in _CURRENT_PLATFORM_BROWSER_GLOBS.values():
        for pattern in patterns:
            if any(browser_dir.glob(pattern)):
                return True
    return False


if __name__ == "__main__":
    raise SystemExit(main())
