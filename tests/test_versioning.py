from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from bao import __version__
from bao.versioning import read_source_version, validate_release_ref, validate_version_configuration

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_read_source_version_matches_runtime_version() -> None:
    assert read_source_version() == __version__


def test_validate_version_configuration_returns_source_version() -> None:
    assert validate_version_configuration() == __version__


def test_validate_release_ref_accepts_matching_tag() -> None:
    validate_release_ref(f"refs/tags/v{__version__}", __version__)


def test_validate_release_ref_rejects_mismatched_tag() -> None:
    with pytest.raises(ValueError, match="does not match expected release ref"):
        validate_release_ref("refs/tags/v9.9.9", __version__)


def test_read_version_script_outputs_single_source_version() -> None:
    result = subprocess.run(
        [sys.executable, "app/scripts/read_version.py"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )

    assert result.stdout.strip() == __version__


def test_validate_release_version_script_accepts_matching_tag() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "app/scripts/validate_release_version.py",
            "--github-ref",
            f"refs/tags/v{__version__}",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )

    assert result.stdout.strip() == __version__


def test_validate_release_version_script_rejects_mismatched_tag() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "app/scripts/validate_release_version.py",
            "--github-ref",
            "refs/tags/v9.9.9",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "does not match expected release ref" in result.stderr
