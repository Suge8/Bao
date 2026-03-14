from __future__ import annotations

import argparse
import shutil
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = PROJECT_ROOT / "app" / "resources"
RUNTIME_BROWSER_RELATIVE_PATH = Path("runtime") / "browser"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Stage desktop app/resources for packaging without bundling the browser runtime twice."
    )
    parser.add_argument(
        "--destination",
        required=True,
        help="Destination directory that will receive a staged copy of app/resources.",
    )
    return parser.parse_args()


def _ignore_browser_runtime(current_dir: str, names: list[str]) -> set[str]:
    current_path = Path(current_dir).resolve(strict=False)
    try:
        relative_path = current_path.relative_to(SOURCE_ROOT)
    except ValueError:
        return set()
    if relative_path == RUNTIME_BROWSER_RELATIVE_PATH.parent and RUNTIME_BROWSER_RELATIVE_PATH.name in names:
        return {RUNTIME_BROWSER_RELATIVE_PATH.name}
    return set()


def main() -> int:
    args = parse_args()
    destination_root = Path(args.destination).expanduser().resolve(strict=False)
    if destination_root.exists():
        shutil.rmtree(destination_root)
    destination_root.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(SOURCE_ROOT, destination_root, ignore=_ignore_browser_runtime)
    print(f"[ok] Staged desktop resources into {destination_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
