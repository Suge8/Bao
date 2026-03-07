from __future__ import annotations

import importlib.util
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Protocol, cast

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = PROJECT_ROOT / "app/scripts/resolve_inno_setup.py"
SPEC = importlib.util.spec_from_file_location("resolve_inno_setup_script", MODULE_PATH)
assert SPEC is not None
assert SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class CandidateCompilerPathsFn(Protocol):
    def __call__(
        self,
        env: Mapping[str, str],
        *,
        which_fn: Callable[[str], str | None],
    ) -> list[Path]: ...


class MissingInnoFilesFn(Protocol):
    def __call__(self, compiler_path: Path) -> list[str]: ...


class ResolveInnoSetupFn(Protocol):
    def __call__(
        self,
        env: Mapping[str, str],
        *,
        which_fn: Callable[[str], str | None],
    ) -> Path | None: ...


candidate_compiler_paths = cast(CandidateCompilerPathsFn, MODULE.candidate_compiler_paths)
missing_inno_files = cast(MissingInnoFilesFn, MODULE.missing_inno_files)
resolve_inno_setup = cast(ResolveInnoSetupFn, MODULE.resolve_inno_setup)


def _which_none(_command: str) -> str | None:
    return None


def _which_compiler(compiler: Path) -> Callable[[str], str | None]:
    def _inner(_command: str) -> str | None:
        return str(compiler)

    return _inner


def _make_compiler(root: Path, *, with_languages: bool = True) -> Path:
    compiler = root / "ISCC.exe"
    compiler.parent.mkdir(parents=True, exist_ok=True)
    _ = compiler.write_text("", encoding="utf-8")
    _ = (root / "Default.isl").write_text("", encoding="utf-8")
    if with_languages:
        lang_dir = root / "Languages"
        lang_dir.mkdir(parents=True, exist_ok=True)
        _ = (lang_dir / "ChineseSimplified.isl").write_text("", encoding="utf-8")
    return compiler


def test_missing_inno_files_reports_required_language_files(tmp_path: Path) -> None:
    compiler = _make_compiler(tmp_path / "Inno Setup 6", with_languages=False)

    assert missing_inno_files(compiler) == ["Languages/ChineseSimplified.isl"]


def test_resolve_inno_setup_prefers_valid_override(tmp_path: Path) -> None:
    valid = _make_compiler(tmp_path / "override" / "Inno Setup 6")
    env = {"BAO_ISCC_EXE": str(valid)}

    resolved = resolve_inno_setup(env, which_fn=_which_none)

    assert resolved == valid


def test_resolve_inno_setup_skips_incomplete_path_candidate(tmp_path: Path) -> None:
    invalid = _make_compiler(tmp_path / "broken" / "Inno Setup 6", with_languages=False)
    valid = _make_compiler(tmp_path / "Program Files (x86)" / "Inno Setup 6")
    env = {
        "BAO_ISCC_EXE": str(invalid),
        "ProgramFiles(x86)": str(tmp_path / "Program Files (x86)"),
    }

    resolved = resolve_inno_setup(env, which_fn=_which_none)

    assert resolved == valid


def test_candidate_compiler_paths_deduplicates_sources(tmp_path: Path) -> None:
    compiler = _make_compiler(tmp_path / "Program Files (x86)" / "Inno Setup 6")
    env = {
        "BAO_ISCC_EXE": str(compiler),
        "ProgramFiles(x86)": str(tmp_path / "Program Files (x86)"),
    }

    candidates = candidate_compiler_paths(env, which_fn=_which_compiler(compiler))

    assert candidates == [compiler]
