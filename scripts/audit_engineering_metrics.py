from __future__ import annotations

import argparse
import ast
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SUFFIXES = (".py", ".qml")
IGNORED_DIR_NAMES = {
    ".git",
    ".venv",
    "__pycache__",
    "dist-pyinstaller",
    "node_modules",
}
DEFAULT_IGNORED_GLOBS = ("bao/skills/**",)
FILE_LINE_LIMIT = 300
FUNCTION_LINE_LIMIT = 60
PARAMETER_LIMIT = 5


@dataclass(frozen=True)
class AuditLimits:
    file_lines: int = FILE_LINE_LIMIT
    function_lines: int = FUNCTION_LINE_LIMIT
    parameters: int = PARAMETER_LIMIT


@dataclass(frozen=True)
class Violation:
    kind: str
    path: Path
    name: str
    value: int
    limit: int
    lineno: int | None = None


@dataclass(frozen=True)
class FunctionMetric:
    name: str
    lineno: int
    line_count: int
    parameter_count: int


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit Bao source files against engineering metric guardrails."
    )
    parser.add_argument("--root", default=str(PROJECT_ROOT))
    parser.add_argument("--file-line-limit", type=int, default=FILE_LINE_LIMIT)
    parser.add_argument("--function-line-limit", type=int, default=FUNCTION_LINE_LIMIT)
    parser.add_argument("--parameter-limit", type=int, default=PARAMETER_LIMIT)
    parser.add_argument(
        "--include-bundled-skills",
        action="store_true",
        help="Include bundled skill implementation files under bao/skills in the audit.",
    )
    parser.add_argument("--fail-on-violation", action="store_true")
    return parser.parse_args(argv)


def is_ignored(path: Path) -> bool:
    return any(part in IGNORED_DIR_NAMES for part in path.parts)


def matches_ignored_glob(path: Path, ignored_globs: tuple[str, ...]) -> bool:
    path_text = path.as_posix()
    for pattern in ignored_globs:
        prefix = pattern.removesuffix("/**")
        if path_text == prefix or path_text.startswith(f"{prefix}/"):
            return True
        if path.match(pattern):
            return True
    return False


def iter_source_files(root: Path, *, ignored_globs: tuple[str, ...] = DEFAULT_IGNORED_GLOBS) -> list[Path]:
    paths: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix not in DEFAULT_SUFFIXES:
            continue
        relative = path.relative_to(root)
        if is_ignored(relative):
            continue
        if matches_ignored_glob(relative, ignored_globs):
            continue
        paths.append(path)
    return sorted(paths)


def read_lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()


def count_nonempty_lines(lines: list[str], start: int, end: int) -> int:
    start_index = max(0, start - 1)
    end_index = min(len(lines), end)
    return sum(1 for line in lines[start_index:end_index] if line.strip())


def effective_parameter_count(node: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    named = [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]
    if named and named[0].arg in {"self", "cls"}:
        named = named[1:]
    count = len(named)
    if node.args.vararg is not None:
        count += 1
    if node.args.kwarg is not None:
        count += 1
    return count


class FunctionMetricCollector(ast.NodeVisitor):
    def __init__(self, lines: list[str]) -> None:
        self._lines = lines
        self._scope: list[str] = []
        self.metrics: list[FunctionMetric] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._scope.append(node.name)
        self.generic_visit(node)
        self._scope.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._record(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._record(node)

    def _record(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        qualified_name = ".".join([*self._scope, node.name]) if self._scope else node.name
        end_lineno = getattr(node, "end_lineno", node.lineno)
        self.metrics.append(
            FunctionMetric(
                name=qualified_name,
                lineno=node.lineno,
                line_count=count_nonempty_lines(self._lines, node.lineno, end_lineno),
                parameter_count=effective_parameter_count(node),
            )
        )
        self._scope.append(node.name)
        self.generic_visit(node)
        self._scope.pop()


def collect_function_metrics(path: Path, lines: list[str]) -> list[FunctionMetric]:
    if path.suffix != ".py":
        return []
    module = ast.parse("\n".join(lines), filename=str(path))
    collector = FunctionMetricCollector(lines)
    collector.visit(module)
    return collector.metrics


def audit_root(
    root: Path,
    *,
    limits: AuditLimits | None = None,
    ignored_globs: tuple[str, ...] = DEFAULT_IGNORED_GLOBS,
) -> list[Violation]:
    active_limits = limits or AuditLimits()
    violations: list[Violation] = []
    for path in iter_source_files(root, ignored_globs=ignored_globs):
        lines = read_lines(path)
        if len(lines) > active_limits.file_lines:
            violations.append(
                Violation(
                    kind="file_lines",
                    path=path,
                    name="",
                    value=len(lines),
                    limit=active_limits.file_lines,
                )
            )
        for metric in collect_function_metrics(path, lines):
            if metric.line_count > active_limits.function_lines:
                violations.append(
                    Violation(
                        kind="function_lines",
                        path=path,
                        name=metric.name,
                        value=metric.line_count,
                        limit=active_limits.function_lines,
                        lineno=metric.lineno,
                    )
                )
            if metric.parameter_count > active_limits.parameters:
                violations.append(
                    Violation(
                        kind="parameter_count",
                        path=path,
                        name=metric.name,
                        value=metric.parameter_count,
                        limit=active_limits.parameters,
                        lineno=metric.lineno,
                    )
                )
    return violations


def format_violation(root: Path, violation: Violation) -> str:
    relative = violation.path.relative_to(root)
    location = f":{violation.lineno}" if violation.lineno is not None else ""
    name = f" {violation.name}" if violation.name else ""
    return (
        f"- {relative}{location}{name} "
        f"(actual={violation.value}, limit={violation.limit})"
    )


def render_report(root: Path, violations: list[Violation], *, limits: AuditLimits | None = None) -> str:
    active_limits = limits or AuditLimits()
    grouped: dict[str, list[Violation]] = defaultdict(list)
    for violation in violations:
        grouped[violation.kind].append(violation)
    lines = [
        "Engineering Metrics Audit",
        f"Root: {root}",
        "Limits: "
        f"file<={active_limits.file_lines}, "
        f"function<={active_limits.function_lines}, "
        f"params<={active_limits.parameters}",
        "",
    ]
    if not violations:
        lines.append("No violations found.")
        return "\n".join(lines)
    title_map = {
        "file_lines": "Files Over Limit",
        "function_lines": "Functions Over Limit",
        "parameter_count": "Functions With Too Many Parameters",
    }
    for kind in ("file_lines", "function_lines", "parameter_count"):
        items = grouped.get(kind)
        if not items:
            continue
        lines.append(f"{title_map[kind]} ({len(items)})")
        for violation in sorted(
            items,
            key=lambda item: (-item.value, str(item.path), item.name, item.lineno or 0),
        ):
            lines.append(format_violation(root, violation))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    root = Path(args.root).expanduser().resolve()
    limits = AuditLimits(
        file_lines=args.file_line_limit,
        function_lines=args.function_line_limit,
        parameters=args.parameter_limit,
    )
    ignored_globs = () if args.include_bundled_skills else DEFAULT_IGNORED_GLOBS
    violations = audit_root(root, limits=limits, ignored_globs=ignored_globs)
    print(render_report(root, violations, limits=limits), end="")
    if args.fail_on_violation and violations:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(__import__("sys").argv[1:]))
