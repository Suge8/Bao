# ruff: noqa: F401, I001
from __future__ import annotations

import json
import re
from pathlib import Path
from unittest.mock import patch

import pytest

from bao.profile import (
    CreateProfileOptions,
    PROFILE_AVATAR_KEYS,
    ProfileRuntimeMetadataOptions,
    ProfileUpdateOptions,
    RenameProfileOptions,
    _has_state_data_roots,
    create_profile,
    delete_profile,
    ensure_profile_registry,
    load_active_profile_snapshot,
    profile_context_from_mapping,
    profile_context_to_dict,
    profile_runtime_metadata,
    rename_profile,
    set_active_profile,
    update_profile,
)


@pytest.fixture()
def fake_home(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))
    return tmp_path


__all__ = [name for name in globals() if not (name.startswith("__") and name.endswith("__"))]
