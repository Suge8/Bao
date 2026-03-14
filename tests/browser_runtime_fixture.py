from __future__ import annotations

import json
from pathlib import Path

from bao.browser import current_browser_platform_key


def write_fake_browser_runtime(root: Path) -> Path:
    runtime_root = root / "runtime"
    platform_key = current_browser_platform_key()
    agent_binary = "agent-browser.exe" if platform_key.startswith("win32-") else "agent-browser"
    browser_binary = "chrome.exe" if platform_key.startswith("win32-") else "chrome"
    agent_browser = runtime_root / "platforms" / platform_key / "bin" / agent_binary
    browser_executable = runtime_root / "platforms" / platform_key / "browser" / browser_binary
    agent_browser.parent.mkdir(parents=True, exist_ok=True)
    browser_executable.parent.mkdir(parents=True, exist_ok=True)
    agent_browser.write_text("#!/bin/sh\n", encoding="utf-8")
    browser_executable.write_text("", encoding="utf-8")
    if agent_browser.suffix != ".exe":
        agent_browser.chmod(0o755)
    (runtime_root / "runtime.json").write_text(
        json.dumps(
            {
                "source": "agent-browser",
                "version": "0.19.0",
                "platforms": {
                    platform_key: {
                        "agentBrowserPath": str(agent_browser.relative_to(runtime_root)),
                        "browserExecutablePath": str(browser_executable.relative_to(runtime_root)),
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    return runtime_root
