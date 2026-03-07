from __future__ import annotations

import os
import shutil
import sys
from collections.abc import Callable, Mapping
from pathlib import Path

_REQUIRED_RELATIVE_FILES = (Path("Default.isl"),)


def _append_unique(candidates: list[Path], seen: set[str], candidate: Path) -> None:
    normalized = os.path.normcase(str(candidate))
    if normalized in seen:
        return
    seen.add(normalized)
    candidates.append(candidate)


def _looks_like_chocolatey_shim(candidate: Path, env: Mapping[str, str]) -> bool:
    if candidate.name.lower() not in {"iscc", "iscc.exe"}:
        return False

    candidate_parent = candidate.parent.name.lower()
    candidate_grandparent = candidate.parent.parent.name.lower()
    if candidate_parent == "bin" and candidate_grandparent == "chocolatey":
        return True

    chocolatey_root = env.get("ChocolateyInstall")
    if not chocolatey_root:
        return False

    try:
        return candidate.is_relative_to(Path(chocolatey_root) / "bin")
    except ValueError:
        return False


def missing_candidate_files(compiler_path: Path, env: Mapping[str, str]) -> list[str]:
    if _looks_like_chocolatey_shim(compiler_path, env):
        return [] if compiler_path.is_file() else ["ISCC.exe"]
    return missing_inno_files(compiler_path)


def candidate_compiler_paths(
    env: Mapping[str, str],
    *,
    which_fn: Callable[[str], str | None] = shutil.which,
) -> list[Path]:
    candidates: list[Path] = []
    seen: set[str] = set()

    override = env.get("BAO_ISCC_EXE")
    if override:
        _append_unique(candidates, seen, Path(override))

    for command in ("iscc.exe", "iscc"):
        found = which_fn(command)
        if found:
            _append_unique(candidates, seen, Path(found))

    for key in ("ProgramFiles(x86)", "ProgramFiles"):
        base = env.get(key)
        if not base:
            continue
        _append_unique(candidates, seen, Path(base) / "Inno Setup 6" / "ISCC.exe")

    return candidates


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
        if not missing_candidate_files(candidate, env):
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
        missing = ", ".join(missing_candidate_files(candidate, env)) or "unknown"
        print(f"Rejected Inno Setup candidate: {candidate} (missing: {missing})", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
