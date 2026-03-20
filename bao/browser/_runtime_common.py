from __future__ import annotations

import platform
import re
import sys
from dataclasses import dataclass

ENV_RUNTIME_ROOT = "BAO_BROWSER_RUNTIME_ROOT"
MANIFEST_NAMES = ("runtime.json", "manifest.json")
RUNTIME_RELATIVE_PATHS = ("app/resources/runtime/browser", "resources/runtime/browser")
AGENT_BROWSER_HOME_CANDIDATES = ("node_modules/agent-browser", "agent-browser")
AGENT_BROWSER_CANDIDATES = (
    "bin/agent-browser",
    "bin/agent-browser.exe",
    "agent-browser",
    "agent-browser.exe",
)
BROWSER_EXECUTABLE_CANDIDATES = (
    "browser/chrome",
    "browser/chrome.exe",
    "browser/chromium",
    "browser/chromium.exe",
    "browser/chrome-linux/chrome",
    "browser/chrome-win/chrome.exe",
    "browser/chrome-mac/Chromium.app/Contents/MacOS/Chromium",
    "browser/chrome-mac/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing",
)
ACTION_ALIASES = {"scroll_into_view": "scrollintoview"}
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
SUPPORTED_ACTION_SET = frozenset(SUPPORTED_BROWSER_ACTIONS)
PATH_ARG_ACTIONS: dict[str, tuple[int, ...]] = {
    "upload": (1,),
    "screenshot": (0,),
    "pdf": (0,),
}
LOCAL_PATH_RE = re.compile(r"^(?:[A-Za-z]:\\|/|~(?:/|$)|\.\.?/)")


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
    normalized_machine = {
        "x86_64": "x64",
        "amd64": "x64",
        "aarch64": "arm64",
        "arm64": "arm64",
    }.get(machine, machine)
    if system.startswith("linux"):
        platform_name = "linux"
    elif system == "darwin":
        platform_name = "darwin"
    elif system in {"win32", "cygwin"}:
        platform_name = "win32"
    else:
        raise RuntimeError(f"Unsupported platform: {system}-{normalized_machine}")
    return f"{platform_name}-{normalized_machine}"


def camel_to_snake(value: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", value).lower()


def looks_like_path(value: str) -> bool:
    return bool(LOCAL_PATH_RE.match(value))
