from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify Bao desktop managed browser runtime before packaging."
    )
    parser.add_argument(
        "--runtime-root",
        default="app/resources/runtime/browser",
        help="Runtime root to verify. Default: app/resources/runtime/browser",
    )
    parser.add_argument(
        "--require-ready",
        action="store_true",
        help="Fail when the managed browser runtime is not ready.",
    )
    return parser.parse_args()


def main() -> int:
    from bao.browser import get_browser_capability_state

    args = parse_args()
    runtime_root = (PROJECT_ROOT / args.runtime_root).resolve(strict=False)
    previous_override = os.environ.get("BAO_BROWSER_RUNTIME_ROOT")
    os.environ["BAO_BROWSER_RUNTIME_ROOT"] = str(runtime_root)
    try:
        state = get_browser_capability_state(enabled=True)
    finally:
        if previous_override is None:
            os.environ.pop("BAO_BROWSER_RUNTIME_ROOT", None)
        else:
            os.environ["BAO_BROWSER_RUNTIME_ROOT"] = previous_override

    require_ready = args.require_ready or os.environ.get("BAO_DESKTOP_REQUIRE_BROWSER_RUNTIME") == "1"
    if state.available:
        print(f"[ok] Managed browser runtime ready: {runtime_root}")
        print(f"      agent-browser: {state.agent_browser_path}")
        print(f"      browser:      {state.browser_executable_path}")
        return 0

    level = "error" if require_ready else "warn"
    print(f"[{level}] Managed browser runtime not ready: {runtime_root}")
    print(f"       reason: {state.reason}")
    print(f"       detail: {state.detail}")
    if require_ready:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
