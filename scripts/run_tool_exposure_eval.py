from __future__ import annotations

import argparse
from pathlib import Path

from bao.agent.tool_exposure_eval import (
    DEFAULT_TOOL_EXPOSURE_CASES_PATH,
    evaluate_tool_exposure_cases,
    load_tool_exposure_cases,
    write_tool_exposure_eval_artifact,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run tool exposure eval and archive JSON output.")
    parser.add_argument(
        "--cases",
        type=Path,
        default=DEFAULT_TOOL_EXPOSURE_CASES_PATH,
        help="Path to the eval cases JSON file.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("artifacts"),
        help="Directory for archived eval JSON results.",
    )
    parser.add_argument(
        "--workspace",
        type=Path,
        default=Path("."),
        help="Workspace path used to build the AgentLoop.",
    )
    args = parser.parse_args()

    payload = evaluate_tool_exposure_cases(
        workspace=args.workspace.resolve(),
        cases=load_tool_exposure_cases(args.cases.resolve()),
    )
    target = write_tool_exposure_eval_artifact(args.output_dir.resolve(), payload)
    print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
