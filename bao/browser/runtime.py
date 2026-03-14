from __future__ import annotations

import asyncio
import json
import os
import platform
import re
import sys
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

from bao.config.paths import get_data_dir

_ENV_RUNTIME_ROOT = "BAO_BROWSER_RUNTIME_ROOT"
_MANIFEST_NAMES = ("runtime.json", "manifest.json")
_RUNTIME_RELATIVE_PATHS = ("app/resources/runtime/browser", "resources/runtime/browser")
_AGENT_BROWSER_HOME_CANDIDATES = ("node_modules/agent-browser", "agent-browser")
_AGENT_BROWSER_CANDIDATES = (
    "bin/agent-browser",
    "bin/agent-browser.exe",
    "agent-browser",
    "agent-browser.exe",
)
_BROWSER_EXECUTABLE_CANDIDATES = (
    "browser/chrome",
    "browser/chrome.exe",
    "browser/chromium",
    "browser/chromium.exe",
    "browser/chrome-linux/chrome",
    "browser/chrome-win/chrome.exe",
    "browser/chrome-mac/Chromium.app/Contents/MacOS/Chromium",
    "browser/chrome-mac/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing",
)
_ACTION_ALIASES = {"scroll_into_view": "scrollintoview"}
SUPPORTED_BROWSER_ACTIONS = (
    "open",
    "back",
    "forward",
    "reload",
    "close",
    "snapshot",
    "click",
    "dblclick",
    "type",
    "fill",
    "press",
    "hover",
    "focus",
    "select",
    "check",
    "uncheck",
    "upload",
    "drag",
    "scroll",
    "scroll_into_view",
    "wait",
    "screenshot",
    "pdf",
    "get",
    "is",
)
_SUPPORTED_ACTION_SET = frozenset(SUPPORTED_BROWSER_ACTIONS)
_PATH_ARG_ACTIONS: dict[str, tuple[int, ...]] = {
    "upload": (1,),
    "screenshot": (0,),
    "pdf": (0,),
}
_LOCAL_PATH_RE = re.compile(r"^(?:[A-Za-z]:\\|/|~(?:/|$)|\.\.?/)")


@dataclass(frozen=True)
class BrowserCapabilityState:
    enabled: bool
    available: bool
    runtime_ready: bool
    runtime_root: str
    runtime_source: str
    profile_path: str
    agent_browser_home_path: str
    agent_browser_path: str
    browser_executable_path: str
    reason: str
    detail: str


def current_browser_platform_key() -> str:
    system = sys.platform
    machine = platform.machine().lower()
    machine_map = {
        "x86_64": "x64",
        "amd64": "x64",
        "aarch64": "arm64",
        "arm64": "arm64",
    }
    normalized_machine = machine_map.get(machine, machine)
    if system.startswith("linux"):
        platform_name = "linux"
    elif system == "darwin":
        platform_name = "darwin"
    elif system in {"win32", "cygwin"}:
        platform_name = "win32"
    else:
        raise RuntimeError(f"Unsupported platform: {system}-{normalized_machine}")
    return f"{platform_name}-{normalized_machine}"


def get_browser_capability_state(*, enabled: bool = True) -> BrowserCapabilityState:
    runtime_root, runtime_source = _resolve_runtime_root()
    profile_path = str((_resolve_profile_dir(create=False)).resolve(strict=False))
    if not enabled:
        return _build_capability_state(
            enabled=False,
            available=False,
            runtime_root=runtime_root,
            runtime_source=runtime_source,
            profile_path=profile_path,
            reason="disabled",
            detail="Browser automation is disabled by config.",
        )
    if runtime_root is None:
        return _build_capability_state(
            enabled=True,
            available=False,
            runtime_root=None,
            runtime_source="missing",
            profile_path=profile_path,
            reason="runtime_missing",
            detail="Managed browser runtime is not bundled yet.",
        )

    manifest = _load_runtime_manifest(runtime_root)
    current_platform = current_browser_platform_key()
    platform_entry = _manifest_platform_entry(manifest, current_platform)
    if _manifest_declares_platforms(manifest) and platform_entry is None:
        return _build_capability_state(
            enabled=True,
            available=False,
            runtime_root=runtime_root,
            runtime_source=runtime_source,
            profile_path=profile_path,
            reason="platform_missing",
            detail=f"Managed browser runtime does not include assets for {current_platform}.",
        )

    agent_browser_path = _resolve_runtime_file(
        runtime_root=runtime_root,
        platform_entry=platform_entry,
        manifest_key="agentBrowserPath",
        fallback_candidates=_AGENT_BROWSER_CANDIDATES,
    )
    agent_browser_home_path = _resolve_runtime_file(
        runtime_root=runtime_root,
        platform_entry=platform_entry,
        manifest_key="agentBrowserHomePath",
        fallback_candidates=_AGENT_BROWSER_HOME_CANDIDATES,
    )
    browser_executable_path = _resolve_runtime_file(
        runtime_root=runtime_root,
        platform_entry=platform_entry,
        manifest_key="browserExecutablePath",
        fallback_candidates=_BROWSER_EXECUTABLE_CANDIDATES,
    )
    if agent_browser_path is None:
        return _build_capability_state(
            enabled=True,
            available=False,
            runtime_root=runtime_root,
            runtime_source=runtime_source,
            profile_path=profile_path,
            agent_browser_home_path=agent_browser_home_path,
            browser_executable_path=browser_executable_path,
            reason="agent_browser_missing",
            detail="Managed browser runtime is missing the agent-browser executable.",
        )
    if agent_browser_home_path is None:
        return _build_capability_state(
            enabled=True,
            available=False,
            runtime_root=runtime_root,
            runtime_source=runtime_source,
            profile_path=profile_path,
            agent_browser_path=agent_browser_path,
            browser_executable_path=browser_executable_path,
            reason="agent_browser_home_missing",
            detail="Managed browser runtime is missing the agent-browser home directory.",
        )
    if not _agent_browser_home_ready(agent_browser_home_path):
        return _build_capability_state(
            enabled=True,
            available=False,
            runtime_root=runtime_root,
            runtime_source=runtime_source,
            profile_path=profile_path,
            agent_browser_home_path=agent_browser_home_path,
            agent_browser_path=agent_browser_path,
            browser_executable_path=browser_executable_path,
            reason="agent_browser_daemon_missing",
            detail="Managed browser runtime is missing agent-browser daemon assets.",
        )
    if browser_executable_path is None:
        return _build_capability_state(
            enabled=True,
            available=False,
            runtime_root=runtime_root,
            runtime_source=runtime_source,
            profile_path=profile_path,
            agent_browser_home_path=agent_browser_home_path,
            agent_browser_path=agent_browser_path,
            reason="browser_executable_missing",
            detail="Managed browser runtime is missing the bundled browser executable.",
        )
    return _build_capability_state(
        enabled=True,
        available=True,
        runtime_root=runtime_root,
        runtime_source=runtime_source,
        profile_path=profile_path,
        agent_browser_home_path=agent_browser_home_path,
        agent_browser_path=agent_browser_path,
        browser_executable_path=browser_executable_path,
        reason="ready",
        detail="Managed browser runtime is ready.",
    )


class BrowserAutomationService:
    def __init__(
        self,
        *,
        workspace: Path,
        enabled: bool = True,
        allowed_dir: Path | None = None,
        timeout_seconds: int = 120,
    ) -> None:
        self.workspace = workspace
        self.allowed_dir = allowed_dir
        self.timeout_seconds = max(5, int(timeout_seconds))
        self._enabled = enabled
        self._context_session: ContextVar[str] = ContextVar(
            "browser_automation_session",
            default="default",
        )

    @property
    def state(self) -> BrowserCapabilityState:
        return get_browser_capability_state(enabled=self._enabled)

    @property
    def available(self) -> bool:
        return self.state.available

    def set_context(self, channel: str, chat_id: str, session_key: str | None = None) -> None:
        base = (
            session_key
            if isinstance(session_key, str) and session_key.strip()
            else f"{channel}:{chat_id}"
        )
        self._context_session.set(self.normalize_session(base))

    @staticmethod
    def normalize_session(value: str) -> str:
        normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip())
        normalized = normalized.strip("-._")
        return (normalized or "default")[:80]

    @staticmethod
    def supports_action(action: str) -> bool:
        return action in _SUPPORTED_ACTION_SET

    async def run(self, *, action: str, args: list[str] | None = None, **options: Any) -> str:
        state = self.state
        if not state.enabled:
            return "Error: browser automation is disabled by config"
        if not state.available:
            return f"Error: managed browser runtime is not ready: {state.detail}"
        if action not in _SUPPORTED_ACTION_SET:
            return "Error: action must be one of the supported browser automation commands"

        normalized_args = args or []
        if not isinstance(normalized_args, list) or not all(
            isinstance(arg, str) for arg in normalized_args
        ):
            return "Error: args must be an array of strings"

        path_error = self._validate_paths(action=action, args=normalized_args)
        if path_error:
            return path_error

        command = self._build_command(
            agent_browser_path=state.agent_browser_path,
            browser_executable_path=state.browser_executable_path,
            profile_path=_resolve_profile_dir(create=True),
            action=action,
            args=normalized_args,
            options=options,
        )
        return await self._run_command(command, env=_build_runtime_environment(state))

    async def smoke_test(self) -> str | None:
        state = self.state
        if not state.available:
            return f"Error: managed browser runtime is not ready: {state.detail}"

        session = self.normalize_session(f"runtime-smoke-{uuid4().hex[:12]}")
        open_result = await self.run(
            action="open",
            args=["about:blank"],
            session=session,
            json_output=False,
        )
        if open_result.startswith("Error:"):
            return open_result

        result: str | None = None
        url_result = await self.run(
            action="get",
            args=["url"],
            session=session,
            json_output=False,
        )
        if url_result.startswith("Error:"):
            result = url_result
        elif url_result.strip() != "about:blank":
            result = (
                f"Error: browser smoke test returned unexpected URL: "
                f"{url_result.strip() or '(empty)'}"
            )

        close_result = await self.run(
            action="close",
            args=[],
            session=session,
            json_output=False,
        )
        if close_result.startswith("Error:"):
            return close_result
        return result

    async def fetch_html(
        self, url: str, *, wait_ms: int = 1500, session: str | None = None
    ) -> dict[str, str]:
        open_error = await self._run_fetch_step("open", [url], session=session)
        if open_error is not None:
            return {"error": open_error}

        wait_error = await self._run_fetch_step("wait", [str(max(wait_ms, 0))], session=session)
        if wait_error is not None:
            return {"error": wait_error}

        html_result = await self.run(
            action="get",
            args=["html", "body"],
            session=session,
            json_output=False,
        )
        if html_result.startswith("Error:"):
            return {"error": html_result}

        final_url = await self.run(action="get", args=["url"], session=session, json_output=False)
        if final_url.startswith("Error:"):
            final_url = url
        return {"html": html_result, "final_url": final_url.strip() or url}

    async def _run_fetch_step(
        self, action: str, args: list[str], *, session: str | None = None
    ) -> str | None:
        result = await self.run(action=action, args=args, session=session, json_output=False)
        if result.startswith("Error:"):
            return result
        return None

    def _build_command(
        self,
        *,
        agent_browser_path: str,
        browser_executable_path: str,
        profile_path: Path,
        action: str,
        args: list[str],
        options: dict[str, Any],
    ) -> list[str]:
        cmd = [agent_browser_path, "--profile", str(profile_path), "--executable-path", browser_executable_path]

        session_value = options.get("session")
        if isinstance(session_value, str) and session_value.strip():
            session_name = self.normalize_session(session_value)
        else:
            session_name = self._context_session.get()
        if session_name:
            cmd.extend(["--session", session_name])

        for key, flag in (
            ("headers_json", "--headers"),
            ("user_agent", "--user-agent"),
            ("proxy", "--proxy"),
        ):
            value = options.get(key)
            if isinstance(value, str) and value.strip():
                cmd.extend([flag, value.strip()])

        if options.get("headed"):
            cmd.append("--headed")
        if options.get("json_output", True):
            cmd.append("--json")
        if options.get("full_page"):
            cmd.append("--full")
        if options.get("annotate"):
            cmd.append("--annotate")
        if options.get("ignore_https_errors"):
            cmd.append("--ignore-https-errors")
        if options.get("allow_file_access"):
            cmd.append("--allow-file-access")

        cmd.append(_ACTION_ALIASES.get(action, action))
        cmd.extend(args)
        return cmd

    def _validate_paths(self, *, action: str, args: list[str]) -> str | None:
        if self.allowed_dir is None:
            return None
        for index in _PATH_ARG_ACTIONS.get(action, ()):
            if index >= len(args):
                continue
            target = args[index].strip()
            if not target:
                continue
            err = self._validate_single_path(target)
            if err:
                return f"Error: path argument {err}"
        return None

    def _validate_single_path(self, raw: str) -> str | None:
        if self.allowed_dir is None:
            return None
        value = urlparse(raw).path if raw.startswith("file://") else raw
        if not _looks_like_path(value):
            return None
        path = Path(value).expanduser()
        if not path.is_absolute():
            path = self.workspace / path
        resolved = path.resolve(strict=False)
        allowed = self.allowed_dir.resolve(strict=False)
        if resolved != allowed and allowed not in resolved.parents:
            return "must stay within the workspace"
        return None

    async def _run_command(self, command: list[str], *, env: dict[str, str]) -> str:
        process: asyncio.subprocess.Process | None = None
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.workspace),
                env=env,
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), timeout=self.timeout_seconds
                )
            except asyncio.TimeoutError:
                process.kill()
                try:
                    await asyncio.wait_for(process.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    pass
                return f"Error: agent-browser timed out after {self.timeout_seconds} seconds"
        except asyncio.CancelledError:
            if process and process.returncode is None:
                process.kill()
                try:
                    await asyncio.wait_for(process.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    pass
            raise
        except Exception as exc:
            return f"Error: agent-browser execution failed: {exc}"

        stdout_text = stdout.decode("utf-8", errors="replace").strip()
        stderr_text = stderr.decode("utf-8", errors="replace").strip()
        if process.returncode == 0:
            return stdout_text or stderr_text or "(no output)"

        detail = stderr_text or stdout_text or "unknown error"
        return f"Error: {detail} (exit code: {process.returncode})"


def _resolve_runtime_root() -> tuple[Path | None, str]:
    env_root = os.environ.get(_ENV_RUNTIME_ROOT, "").strip()
    if env_root:
        path = Path(env_root).expanduser().resolve(strict=False)
        return (path, "env") if path.exists() else (None, "env")

    for root in _runtime_candidate_roots():
        for relative_path in _RUNTIME_RELATIVE_PATHS:
            candidate = (root / relative_path).resolve(strict=False)
            if candidate.exists():
                return candidate, "bundled"
    return None, "missing"


def _runtime_candidate_roots() -> list[Path]:
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


def _resolve_runtime_file(
    *,
    runtime_root: Path,
    platform_entry: dict[str, object] | None,
    manifest_key: str,
    fallback_candidates: tuple[str, ...],
) -> Path | None:
    manifest_value = _manifest_path_value(platform_entry, manifest_key)
    if manifest_value is not None:
        candidate = (runtime_root / manifest_value).resolve(strict=False)
        if candidate.exists():
            return candidate
    if platform_entry is not None:
        return None
    for relative_path in fallback_candidates:
        candidate = (runtime_root / relative_path).resolve(strict=False)
        if candidate.exists():
            return candidate
    return None


def _agent_browser_home_ready(agent_browser_home_path: Path) -> bool:
    return (
        agent_browser_home_path.is_dir()
        and (agent_browser_home_path / "package.json").is_file()
        and (agent_browser_home_path / "bin" / "agent-browser.js").is_file()
    )


def _build_runtime_environment(state: BrowserCapabilityState) -> dict[str, str]:
    env = os.environ.copy()
    if state.agent_browser_home_path:
        env["AGENT_BROWSER_HOME"] = state.agent_browser_home_path
    return env


def _load_runtime_manifest(runtime_root: Path) -> dict[str, object]:
    for name in _MANIFEST_NAMES:
        path = runtime_root / name
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        return data if isinstance(data, dict) else {}
    return {}


def _manifest_declares_platforms(manifest: dict[str, object]) -> bool:
    platforms = manifest.get("platforms")
    return isinstance(platforms, dict)


def _manifest_platform_entry(
    manifest: dict[str, object], platform_key: str
) -> dict[str, object] | None:
    platforms = manifest.get("platforms")
    if not isinstance(platforms, dict):
        return None
    entry = platforms.get(platform_key)
    return entry if isinstance(entry, dict) else None


def _manifest_path_value(
    platform_entry: dict[str, object] | None, manifest_key: str
) -> str | None:
    if platform_entry is None:
        return None
    value = platform_entry.get(manifest_key) or platform_entry.get(_camel_to_snake(manifest_key))
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _resolve_profile_dir(*, create: bool) -> Path:
    path = get_data_dir() / "browser" / "profile"
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def _camel_to_snake(value: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", value).lower()


def _looks_like_path(value: str) -> bool:
    return bool(_LOCAL_PATH_RE.match(value))


def _build_capability_state(
    *,
    enabled: bool,
    available: bool,
    runtime_root: Path | None,
    runtime_source: str,
    profile_path: str,
    reason: str,
    detail: str,
    agent_browser_home_path: Path | None = None,
    agent_browser_path: Path | None = None,
    browser_executable_path: Path | None = None,
) -> BrowserCapabilityState:
    return BrowserCapabilityState(
        enabled=enabled,
        available=available,
        runtime_ready=available,
        runtime_root=str(runtime_root) if runtime_root else "",
        runtime_source=runtime_source,
        profile_path=profile_path,
        agent_browser_home_path=str(agent_browser_home_path or ""),
        agent_browser_path=str(agent_browser_path or ""),
        browser_executable_path=str(browser_executable_path or ""),
        reason=reason,
        detail=detail,
    )
