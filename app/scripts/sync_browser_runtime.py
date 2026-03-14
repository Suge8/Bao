from __future__ import annotations

import argparse
import shutil
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DESTINATION_ROOT = PROJECT_ROOT / "app" / "resources" / "runtime" / "browser"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sync a prepared managed browser runtime into Bao desktop resources."
    )
    parser.add_argument(
        "--source",
        required=True,
        help="Source directory containing runtime.json, agent-browser, and bundled browser files.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source_root = Path(args.source).expanduser().resolve(strict=False)
    if not source_root.is_dir():
        raise SystemExit(f"Source runtime directory not found: {source_root}")

    DESTINATION_ROOT.mkdir(parents=True, exist_ok=True)
    for child in DESTINATION_ROOT.iterdir():
        if child.name == "README.md":
            continue
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()

    for child in source_root.iterdir():
        target = DESTINATION_ROOT / child.name
        if child.is_dir():
            shutil.copytree(child, target)
        else:
            shutil.copy2(child, target)

    print(f"[ok] Synced managed browser runtime into {DESTINATION_ROOT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
