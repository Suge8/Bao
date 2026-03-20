# ruff: noqa: F401
from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Callable, cast

import pytest

from bao.agent.tool_result import ToolTextResult
from bao.utils.helpers import safe_filename

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _artifact_store_class() -> Any:
    module_path = PROJECT_ROOT / "bao" / "agent" / "artifacts.py"
    module_name = "_artifact_store_mod"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return getattr(module, "ArtifactStore")


def _make_store(tmp_path: Path, session_key: str, retention_days: int = 7) -> Any:
    store_cls = _artifact_store_class()
    return store_cls(tmp_path, session_key, retention_days)


class _StaticProvider:
    async def chat(self, *args: Any, **kwargs: Any):
        del args, kwargs
        from bao.providers.base import LLMResponse

        return LLMResponse(content="ok", finish_reason="stop")

    def get_default_model(self) -> str:
        return "test-model"


__all__ = [name for name in globals() if not (name.startswith("__") and name.endswith("__"))]
