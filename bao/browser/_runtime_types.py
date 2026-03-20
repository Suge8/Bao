from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RuntimeContext:
    runtime_root: Path
    runtime_source: str
    profile_path: str


@dataclass(frozen=True)
class RuntimeComponents:
    agent_browser_home_path: Path | None = None
    agent_browser_path: Path | None = None
    browser_executable_path: Path | None = None


@dataclass(frozen=True)
class RuntimeFileLookup:
    platform_entry: dict[str, object] | None
    manifest_key: str
    fallback_candidates: tuple[str, ...]


@dataclass(frozen=True)
class CapabilityStateDraft:
    enabled: bool
    available: bool
    runtime_root: Path | None
    runtime_source: str
    profile_path: str
    components: RuntimeComponents = RuntimeComponents()
