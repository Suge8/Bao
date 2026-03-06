from __future__ import annotations

import ast
import tomllib
from pathlib import Path
from typing import cast

VERSION_SOURCE_PATH = Path(__file__).with_name("__about__.py")
PYPROJECT_PATH = VERSION_SOURCE_PATH.parent.parent / "pyproject.toml"
HATCH_VERSION_PATH = "bao/__about__.py"


def read_source_version(version_file: Path = VERSION_SOURCE_PATH) -> str:
    module = ast.parse(version_file.read_text(encoding="utf-8"), filename=str(version_file))
    for node in module.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "__version__":
                    value = node.value
                    if (
                        isinstance(value, ast.Constant)
                        and isinstance(value.value, str)
                        and value.value
                    ):
                        return value.value
                    raise ValueError(
                        f"__version__ in {version_file} must be a non-empty string literal"
                    )
    raise ValueError(f"Missing __version__ in {version_file}")


def validate_version_configuration(
    pyproject_path: Path = PYPROJECT_PATH, version_file: Path = VERSION_SOURCE_PATH
) -> str:
    version = read_source_version(version_file)
    data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))

    project = data.get("project")
    if not isinstance(project, dict):
        raise ValueError("Missing [project] table in pyproject.toml")
    project_dict = cast(dict[str, object], project)

    if "version" in project_dict:
        raise ValueError("[project].version must be removed; version should be sourced dynamically")

    dynamic = project_dict.get("dynamic")
    if not isinstance(dynamic, list) or "version" not in dynamic:
        raise ValueError("[project].dynamic must include 'version'")

    tool = data.get("tool")
    if not isinstance(tool, dict):
        raise ValueError("Missing [tool] table in pyproject.toml")
    hatch = cast(dict[str, object], tool).get("hatch")
    if not isinstance(hatch, dict):
        raise ValueError("Missing [tool.hatch] table in pyproject.toml")
    hatch_version = cast(dict[str, object], hatch).get("version")
    if not isinstance(hatch_version, dict):
        raise ValueError("Missing [tool.hatch.version] table in pyproject.toml")

    version_path = cast(dict[str, object], hatch_version).get("path")
    if version_path != HATCH_VERSION_PATH:
        raise ValueError(
            f"[tool.hatch.version].path must be {HATCH_VERSION_PATH!r}, got {version_path!r}"
        )

    return version


def validate_release_ref(github_ref: str, version: str) -> None:
    if not github_ref.startswith("refs/tags/"):
        return

    expected_ref = f"refs/tags/v{version}"
    if github_ref != expected_ref:
        raise ValueError(
            f"Git ref {github_ref!r} does not match expected release ref {expected_ref!r}"
        )
