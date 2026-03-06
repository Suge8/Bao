from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import cast

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def main() -> int:
    from bao.versioning import validate_release_ref, validate_version_configuration

    parser = argparse.ArgumentParser()
    _ = parser.add_argument("--github-ref", default="", type=str)
    args = parser.parse_args()
    github_ref = cast(str, args.github_ref)

    version = validate_version_configuration()
    validate_release_ref(github_ref, version)
    print(version)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
