from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def main() -> int:
    from bao.versioning import read_source_version

    print(read_source_version())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
