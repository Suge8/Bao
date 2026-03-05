from __future__ import annotations

import tomllib
from pathlib import Path
from typing import cast


def main() -> int:
    data: dict[str, object] = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    project = data.get("project")
    if not isinstance(project, dict):
        raise KeyError("Missing [project] in pyproject.toml")

    project_dict = cast(dict[str, object], project)
    version = project_dict.get("version")
    if not isinstance(version, str):
        raise TypeError("project.version must be a string")

    print(version)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
