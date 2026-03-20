from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from bao.config.paths import get_data_dir

from ._runtime_common import (
    AGENT_BROWSER_CANDIDATES,
    AGENT_BROWSER_HOME_CANDIDATES,
    BROWSER_EXECUTABLE_CANDIDATES,
    ENV_RUNTIME_ROOT,
    MANIFEST_NAMES,
    RUNTIME_RELATIVE_PATHS,
    BrowserCapabilityState,
    camel_to_snake,
    current_browser_platform_key,
)
from ._runtime_types import (
    CapabilityStateDraft,
    RuntimeComponents,
    RuntimeContext,
    RuntimeFileLookup,
)


def get_browser_capability_state(*, enabled: bool = True) -> BrowserCapabilityState:
    runtime_root, runtime_source = resolve_runtime_root()
    profile_path = str(resolve_profile_dir(create=False).resolve(strict=False))
    if not enabled:
        return build_capability_state(
            CapabilityStateDraft(
                enabled=False,
                available=False,
                runtime_root=runtime_root,
                runtime_source=runtime_source,
                profile_path=profile_path,
            ),
            reason="disabled",
            detail="Browser automation is disabled by config.",
        )
    if runtime_root is None:
        return build_capability_state(
            CapabilityStateDraft(
                enabled=True,
                available=False,
                runtime_root=None,
                runtime_source="missing",
                profile_path=profile_path,
            ),
            reason="runtime_missing",
            detail="Managed browser runtime is not bundled yet.",
        )
    context = RuntimeContext(
        runtime_root=runtime_root,
        runtime_source=runtime_source,
        profile_path=profile_path,
    )
    manifest = load_runtime_manifest(runtime_root)
    platform_entry = manifest_platform_entry(manifest, current_browser_platform_key())
    if manifest_declares_platforms(manifest) and platform_entry is None:
        return build_capability_state(
            CapabilityStateDraft(
                enabled=True,
                available=False,
                runtime_root=runtime_root,
                runtime_source=runtime_source,
                profile_path=profile_path,
            ),
            reason="platform_missing",
            detail=missing_platform_detail(),
        )
    return build_ready_state(context, platform_entry)


def missing_platform_detail() -> str:
    current_platform = current_browser_platform_key()
    return f"Managed browser runtime does not include assets for {current_platform}."


def build_ready_state(
    context: RuntimeContext,
    platform_entry: dict[str, object] | None,
) -> BrowserCapabilityState:
    agent_browser_path = resolve_runtime_file(
        context.runtime_root,
        RuntimeFileLookup(platform_entry, "agentBrowserPath", AGENT_BROWSER_CANDIDATES),
    )
    agent_browser_home_path = resolve_runtime_file(
        context.runtime_root,
        RuntimeFileLookup(platform_entry, "agentBrowserHomePath", AGENT_BROWSER_HOME_CANDIDATES),
    )
    browser_executable_path = resolve_runtime_file(
        context.runtime_root,
        RuntimeFileLookup(platform_entry, "browserExecutablePath", BROWSER_EXECUTABLE_CANDIDATES),
    )
    components = RuntimeComponents(
        agent_browser_home_path=agent_browser_home_path,
        agent_browser_path=agent_browser_path,
        browser_executable_path=browser_executable_path,
    )
    missing = missing_runtime_component(context, components)
    if missing is not None:
        return missing
    return build_capability_state(
        CapabilityStateDraft(
            enabled=True,
            available=True,
            runtime_root=context.runtime_root,
            runtime_source=context.runtime_source,
            profile_path=context.profile_path,
            components=components,
        ),
        reason="ready",
        detail="Managed browser runtime is ready.",
    )


def missing_runtime_component(
    context: RuntimeContext,
    components: RuntimeComponents,
) -> BrowserCapabilityState | None:
    draft = CapabilityStateDraft(
        enabled=True,
        available=False,
        runtime_root=context.runtime_root,
        runtime_source=context.runtime_source,
        profile_path=context.profile_path,
        components=components,
    )
    if components.agent_browser_path is None:
        return build_capability_state(
            draft,
            reason="agent_browser_missing",
            detail="Managed browser runtime is missing the agent-browser executable.",
        )
    if components.agent_browser_home_path is None:
        return build_capability_state(
            draft,
            reason="agent_browser_home_missing",
            detail="Managed browser runtime is missing the agent-browser home directory.",
        )
    if not agent_browser_home_ready(components.agent_browser_home_path):
        return build_capability_state(
            draft,
            reason="agent_browser_daemon_missing",
            detail="Managed browser runtime is missing agent-browser daemon assets.",
        )
    if components.browser_executable_path is None:
        return build_capability_state(
            draft,
            reason="browser_executable_missing",
            detail="Managed browser runtime is missing the bundled browser executable.",
        )
    return None


def resolve_runtime_root() -> tuple[Path | None, str]:
    env_root = os.environ.get(ENV_RUNTIME_ROOT, "").strip()
    if env_root:
        path = Path(env_root).expanduser().resolve(strict=False)
        return (path, "env") if path.exists() else (None, "env")
    for root in runtime_candidate_roots():
        for relative_path in RUNTIME_RELATIVE_PATHS:
            candidate = (root / relative_path).resolve(strict=False)
            if candidate.exists():
                return candidate, "bundled"
    return None, "missing"


def runtime_candidate_roots() -> list[Path]:
    repo_root = Path(__file__).resolve().parents[2]
    exe = Path(sys.executable).resolve()
    roots = [repo_root]
    meipass = getattr(sys, "_MEIPASS", "")
    if meipass:
        roots.append(Path(meipass))
    roots.extend([exe.parent, exe.parent.parent / "Resources"])
    unique_roots: list[Path] = []
    seen: set[Path] = set()
    for root in roots:
        resolved = root.resolve(strict=False)
        if resolved in seen:
            continue
        seen.add(resolved)
        unique_roots.append(resolved)
    return unique_roots


def resolve_runtime_file(
    runtime_root: Path,
    lookup: RuntimeFileLookup,
) -> Path | None:
    manifest_value = manifest_path_value(lookup.platform_entry, lookup.manifest_key)
    if manifest_value is not None:
        candidate = (runtime_root / manifest_value).resolve(strict=False)
        return candidate if candidate.exists() else None
    if lookup.platform_entry is not None:
        return None
    for relative_path in lookup.fallback_candidates:
        candidate = (runtime_root / relative_path).resolve(strict=False)
        if candidate.exists():
            return candidate
    return None


def agent_browser_home_ready(agent_browser_home_path: Path) -> bool:
    return (
        agent_browser_home_path.is_dir()
        and (agent_browser_home_path / "package.json").is_file()
        and (agent_browser_home_path / "bin" / "agent-browser.js").is_file()
    )


def build_runtime_environment(state: BrowserCapabilityState) -> dict[str, str]:
    env = os.environ.copy()
    if state.agent_browser_home_path:
        env["AGENT_BROWSER_HOME"] = state.agent_browser_home_path
    return env


def load_runtime_manifest(runtime_root: Path) -> dict[str, object]:
    for name in MANIFEST_NAMES:
        path = runtime_root / name
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        return data if isinstance(data, dict) else {}
    return {}


def manifest_declares_platforms(manifest: dict[str, object]) -> bool:
    return isinstance(manifest.get("platforms"), dict)


def manifest_platform_entry(
    manifest: dict[str, object], platform_key: str
) -> dict[str, object] | None:
    platforms = manifest.get("platforms")
    if not isinstance(platforms, dict):
        return None
    entry = platforms.get(platform_key)
    return entry if isinstance(entry, dict) else None


def manifest_path_value(platform_entry: dict[str, object] | None, manifest_key: str) -> str | None:
    if platform_entry is None:
        return None
    value = platform_entry.get(manifest_key) or platform_entry.get(camel_to_snake(manifest_key))
    return value.strip() if isinstance(value, str) and value.strip() else None


def resolve_profile_dir(*, create: bool) -> Path:
    path = get_data_dir() / "browser" / "profile"
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def build_capability_state(
    draft: CapabilityStateDraft,
    reason: str,
    detail: str,
) -> BrowserCapabilityState:
    return BrowserCapabilityState(
        enabled=draft.enabled,
        available=draft.available,
        runtime_ready=draft.available,
        runtime_root=str(draft.runtime_root) if draft.runtime_root else "",
        runtime_source=draft.runtime_source,
        profile_path=draft.profile_path,
        agent_browser_home_path=str(draft.components.agent_browser_home_path or ""),
        agent_browser_path=str(draft.components.agent_browser_path or ""),
        browser_executable_path=str(draft.components.browser_executable_path or ""),
        reason=reason,
        detail=detail,
    )
