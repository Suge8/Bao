from __future__ import annotations

import argparse
import html
import shutil
import subprocess
import sys
import sysconfig
import tempfile
from pathlib import Path

import PySide6

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_QML_ROOT = PROJECT_ROOT / "app" / "qml"
DEFAULT_RESOURCES_ROOT = PROJECT_ROOT / "app" / "resources"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a binary RCC bundle for desktop QML and runtime assets."
    )
    parser.add_argument("--output-rcc", required=True, help="Path to the generated .rcc file.")
    parser.add_argument(
        "--qml-root",
        default=str(DEFAULT_QML_ROOT),
        help="Root directory containing desktop QML files.",
    )
    parser.add_argument(
        "--resources-root",
        default=str(DEFAULT_RESOURCES_ROOT),
        help="Root directory containing desktop runtime resources.",
    )
    parser.add_argument(
        "--output-qrc",
        default="",
        help="Optional debug output path for the generated .qrc manifest.",
    )
    parser.add_argument(
        "--with-qml-cache",
        action="store_true",
        help="Also embed qmlcachegen bytecode artifacts into the resource bundle.",
    )
    return parser.parse_args()


def _qt_tool_path(name: str) -> Path:
    pyside_root = Path(PySide6.__file__).resolve().parent
    executable_dir = Path(sys.executable).resolve().parent
    scripts_dir = Path(sysconfig.get_path("scripts") or executable_dir)
    tool_names = [name]
    if not name.startswith("pyside6-"):
        tool_names.append(f"pyside6-{name}")
    suffixes = ("", ".exe", ".bat", ".cmd")
    candidates: list[Path] = []
    for base_dir in (
        pyside_root / "Qt" / "libexec",
        pyside_root / "Qt" / "bin",
        scripts_dir,
        executable_dir,
        pyside_root / "scripts",
    ):
        for tool_name in tool_names:
            for suffix in suffixes:
                candidate = base_dir / f"{tool_name}{suffix}"
                if candidate not in candidates:
                    candidates.append(candidate)
    for candidate in candidates:
        if candidate.exists():
            return candidate
    for tool_name in tool_names:
        resolved = shutil.which(tool_name)
        if resolved:
            return Path(resolved)
    raise FileNotFoundError(f"Qt tool not found: {name}")


def _iter_files(root: Path, *, skip_paths: set[Path] | None = None) -> list[Path]:
    if not root.exists():
        return []
    skipped = {path.resolve() for path in (skip_paths or set())}
    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and path.resolve() not in skipped
    )


def _qrc_entries(root: Path, *, prefix: str, skip_paths: set[Path] | None = None) -> list[str]:
    entries: list[str] = []
    for path in _iter_files(root, skip_paths=skip_paths):
        alias = path.relative_to(root).as_posix()
        entries.append(
            f'    <file alias="{html.escape(alias)}">{html.escape(path.as_posix())}</file>'
        )
    if not entries:
        return []
    return [f'  <qresource prefix="{prefix}">', *entries, "  </qresource>"]


def _compiled_alias(path: Path) -> str:
    if path.suffix == ".qml":
        return f"{path.as_posix()}c"
    if path.suffix in {".js", ".mjs"}:
        return f"{path.as_posix()}c"
    return path.as_posix()


def _generate_qml_cache_entries(qml_root: Path, cache_root: Path) -> list[str]:
    qmlcachegen = _qt_tool_path("qmlcachegen")
    entries: list[str] = []
    for source_path in _iter_files(qml_root):
        if source_path.suffix not in {".qml", ".js", ".mjs"}:
            continue
        relative_path = source_path.relative_to(qml_root)
        output_path = cache_root / _compiled_alias(relative_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        resource_path = f"/app/qml/{relative_path.as_posix()}"
        subprocess.run(
            [
                str(qmlcachegen),
                "--only-bytecode",
                "-I",
                str(qml_root),
                "--resource-path",
                resource_path,
                "-o",
                str(output_path),
                str(source_path),
            ],
            check=True,
        )
        entries.append(
            f'    <file alias="{html.escape(_compiled_alias(relative_path))}">'
            f"{html.escape(output_path.as_posix())}</file>"
        )
    return entries


def build_qrc_text(
    qml_root: Path,
    resources_root: Path,
    *,
    cache_root: Path,
    with_qml_cache: bool,
    skip_resource_paths: set[Path] | None = None,
) -> str:
    qml_entries = _qrc_entries(qml_root, prefix="/app/qml")
    if qml_entries and with_qml_cache:
        compiled_entries = _generate_qml_cache_entries(qml_root, cache_root)
        if compiled_entries:
            qml_entries = qml_entries[:-1] + compiled_entries + [qml_entries[-1]]
    resource_entries = _qrc_entries(
        resources_root,
        prefix="/app/resources",
        skip_paths=skip_resource_paths,
    )
    lines = ["<RCC>"]
    lines.extend(qml_entries)
    lines.extend(resource_entries)
    lines.append("</RCC>")
    return "\n".join(lines) + "\n"


def main() -> int:
    args = parse_args()
    qml_root = Path(args.qml_root).expanduser().resolve(strict=True)
    resources_root = Path(args.resources_root).expanduser().resolve(strict=True)
    output_rcc = Path(args.output_rcc).expanduser().resolve(strict=False)
    output_rcc.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="bao-qml-rcc-") as temp_dir:
        cache_root = Path(temp_dir) / "cache"
        cache_root.mkdir(parents=True, exist_ok=True)
        qrc_text = build_qrc_text(
            qml_root,
            resources_root,
            cache_root=cache_root,
            with_qml_cache=bool(args.with_qml_cache),
            skip_resource_paths={output_rcc},
        )
        if args.output_qrc:
            output_qrc = Path(args.output_qrc).expanduser().resolve(strict=False)
            output_qrc.parent.mkdir(parents=True, exist_ok=True)
            output_qrc.write_text(qrc_text, encoding="utf-8")
        qrc_path = Path(temp_dir) / "desktop_qml.qrc"
        qrc_path.write_text(qrc_text, encoding="utf-8")
        subprocess.run(
            [
                str(_qt_tool_path("rcc")),
                "--binary",
                str(qrc_path),
                "-o",
                str(output_rcc),
            ],
            check=True,
        )
    print(f"[ok] Built desktop QML resource bundle: {output_rcc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
