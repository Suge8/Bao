# ruff: noqa: F401
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from bao.agent.skills import SkillsLoader

SKILL_DIR = Path(__file__).parent.parent / "bao" / "skills"
CODING_AGENT_SKILL_DIR = SKILL_DIR / "coding-agent"
AGENT_BROWSER_SKILL_DIR = SKILL_DIR / "agent-browser"
SETUP_SCRIPT = CODING_AGENT_SKILL_DIR / "scripts" / "setup-project.sh"


__all__ = [name for name in globals() if not (name.startswith("__") and name.endswith("__"))]
