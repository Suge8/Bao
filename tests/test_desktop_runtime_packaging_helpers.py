from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_stage_desktop_resources_excludes_browser_runtime(tmp_path: Path) -> None:
    destination = tmp_path / "staged-resources"

    subprocess.run(
        [
            sys.executable,
            "app/scripts/stage_desktop_resources.py",
            "--destination",
            str(destination),
        ],
        check=True,
        cwd=PROJECT_ROOT,
    )

    assert (destination / "logo.ico").is_file()
    assert not (destination / "runtime" / "browser").exists()


def test_sync_browser_runtime_supports_explicit_destination(tmp_path: Path) -> None:
    source = tmp_path / "source-runtime"
    destination = tmp_path / "embedded-runtime"
    (source / "node_modules" / "agent-browser" / "bin").mkdir(parents=True, exist_ok=True)
    (source / "platforms" / "win32-x64" / "bin").mkdir(parents=True, exist_ok=True)
    (source / "runtime.json").write_text("{}", encoding="utf-8")
    (source / "README.md").write_text("runtime", encoding="utf-8")
    (source / "node_modules" / "agent-browser" / "package.json").write_text(
        '{"name":"agent-browser"}\n',
        encoding="utf-8",
    )
    (source / "node_modules" / "agent-browser" / "bin" / "agent-browser.js").write_text(
        "#!/usr/bin/env node\n",
        encoding="utf-8",
    )

    subprocess.run(
        [
            sys.executable,
            "app/scripts/sync_browser_runtime.py",
            "--source",
            str(source),
            "--destination",
            str(destination),
        ],
        check=True,
        cwd=PROJECT_ROOT,
    )

    assert (destination / "runtime.json").is_file()
    assert (destination / "node_modules" / "agent-browser" / "bin" / "agent-browser.js").is_file()
