from __future__ import annotations

from pathlib import Path


def main() -> int:
    path = Path("app/scripts/build_win.bat")
    lines = path.read_text(encoding="utf-8").splitlines()

    start = -1
    for idx, raw in enumerate(lines):
        if raw.strip().lower() == "uv run python -m nuitka ^":
            start = idx
            break

    if start < 0:
        print("ERROR: cannot find 'python -m nuitka ^' block")
        return 1

    for i in range(start + 1, len(lines)):
        stripped = lines[i].strip()

        if not stripped:
            print(f"ERROR: blank line inside Nuitka continuation block at line {i + 1}")
            return 1

        if stripped.upper().startswith("REM"):
            print(f"ERROR: REM comment inside Nuitka continuation block at line {i + 1}")
            return 1

        if stripped.endswith("^"):
            continue

        break

    print("build_win.bat continuation block looks valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
