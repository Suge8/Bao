from __future__ import annotations

import os
import shutil
import sys
from collections.abc import Callable, Mapping
from pathlib import Path

_REQUIRED_RELATIVE_FILES = (
    Path("Default.isl"),
    Path("Languages") / "ChineseSimplified.isl",
)


def candidate_compiler_paths(
    env: Mapping[str, str],
    *,
    which_fn: Callable[[str], str | None] = shutil.which,
) -> list[Path]:
    candidates: list[Path] = []

    override = env.get("BAO_ISCC_EXE")
    if override:
        candidates.append(Path(override))

    for command in ("iscc.exe", "iscc"):
        found = which_fn(command)
        if found:
            candidates.append(Path(found))

    for key in ("ProgramFiles(x86)", "ProgramFiles"):
        base = env.get(key)
        if not base:
            continue
        candidates.append(Path(base) / "Inno Setup 6" / "ISCC.exe")

    unique: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        normalized = os.path.normcase(str(candidate))
        if normalized in seen:
            continue
        seen.add(normalized)
        unique.append(candidate)

    return unique


def missing_inno_files(compiler_path: Path) -> list[str]:
    missing: list[str] = []
    if not compiler_path.is_file():
        missing.append("ISCC.exe")
        return missing

    compiler_root = compiler_path.parent
    for rel_path in _REQUIRED_RELATIVE_FILES:
        if not (compiler_root / rel_path).is_file():
            missing.append(rel_path.as_posix())

    return missing


def resolve_inno_setup(
    env: Mapping[str, str],
    *,
    which_fn: Callable[[str], str | None] = shutil.which,
) -> Path | None:
    for candidate in candidate_compiler_paths(env, which_fn=which_fn):
        if not missing_inno_files(candidate):
            return candidate
    return None


def main() -> int:
    env = dict(os.environ)
    candidates = candidate_compiler_paths(env)
    resolved = resolve_inno_setup(env)
    if resolved is not None:
        print(resolved)
        return 0

    if not candidates:
        print(
            "Inno Setup compiler was not found in BAO_ISCC_EXE, PATH, or standard install directories.",
            file=sys.stderr,
        )
        return 1

    for candidate in candidates:
        missing = ", ".join(missing_inno_files(candidate)) or "unknown"
        print(f"Rejected Inno Setup candidate: {candidate} (missing: {missing})", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
