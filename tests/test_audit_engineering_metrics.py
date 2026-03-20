from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

SCRIPT_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "audit_engineering_metrics.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location("audit_engineering_metrics_test_module", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_audit_root_reports_file_and_function_violations(tmp_path: Path) -> None:
    module = _load_module()
    script_path = tmp_path / "sample.py"
    script_path.write_text(
        "\n".join(
            [
                "def oversized_function(a, b, c, d, e, f):",
                *["    x = 1" for _ in range(61)],
                "    return x",
                *["# filler" for _ in range(340)],
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    violations = module.audit_root(tmp_path)
    kinds = {(item.kind, item.name) for item in violations}

    assert ("file_lines", "") in kinds
    assert ("function_lines", "oversized_function") in kinds
    assert ("parameter_count", "oversized_function") in kinds


def test_audit_root_ignores_self_for_parameter_limit(tmp_path: Path) -> None:
    module = _load_module()
    script_path = tmp_path / "sample.py"
    script_path.write_text(
        "\n".join(
            [
                "class Example:",
                "    def ok(self, first, second, third):",
                "        return first + second + third",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    violations = module.audit_root(tmp_path)
    assert not [item for item in violations if item.kind == "parameter_count"]


def test_audit_root_ignores_common_generated_directories(tmp_path: Path) -> None:
    module = _load_module()
    generated = tmp_path / ".venv" / "ignored.py"
    generated.parent.mkdir(parents=True)
    generated.write_text("\n".join(["x = 1" for _ in range(450)]) + "\n", encoding="utf-8")

    violations = module.audit_root(tmp_path)
    assert violations == []


def test_audit_root_respects_custom_limits(tmp_path: Path) -> None:
    module = _load_module()
    script_path = tmp_path / "sample.py"
    script_path.write_text(
        "\n".join(
            [
                "def compact(a, b, c):",
                "    return a + b + c",
                *["# filler" for _ in range(3)],
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    limits = module.AuditLimits(file_lines=4, function_lines=1, parameters=2)
    violations = module.audit_root(tmp_path, limits=limits)
    report = module.render_report(tmp_path, violations, limits=limits)

    assert {item.kind for item in violations} == {
        "file_lines",
        "function_lines",
        "parameter_count",
    }
    assert "Limits: file<=4, function<=1, params<=2" in report


def test_audit_root_ignores_bundled_skills_by_default(tmp_path: Path) -> None:
    module = _load_module()
    skill_path = tmp_path / "bao" / "skills" / "demo" / "scripts" / "tool.py"
    skill_path.parent.mkdir(parents=True)
    skill_path.write_text(
        "\n".join(
            [
                "def oversized(a, b, c, d, e, f):",
                *["    x = 1" for _ in range(61)],
                "    return x",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    violations = module.audit_root(tmp_path)

    assert violations == []


def test_audit_root_can_include_bundled_skills(tmp_path: Path) -> None:
    module = _load_module()
    skill_path = tmp_path / "bao" / "skills" / "demo" / "scripts" / "tool.py"
    skill_path.parent.mkdir(parents=True)
    skill_path.write_text(
        "\n".join(
            [
                "def oversized(a, b, c, d, e, f):",
                *["    x = 1" for _ in range(61)],
                "    return x",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    violations = module.audit_root(tmp_path, ignored_globs=())
    kinds = {(item.kind, item.name) for item in violations}

    assert ("function_lines", "oversized") in kinds
    assert ("parameter_count", "oversized") in kinds
