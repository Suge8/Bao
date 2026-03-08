from __future__ import annotations

import hashlib
import os
import platform
import shlex
import subprocess
import sys
import tempfile
from collections.abc import Coroutine
from pathlib import Path
from typing import Any, Callable, ClassVar, Protocol, TypeVar, cast
from urllib.parse import urlparse

import httpx
from PySide6.QtCore import Property, QObject, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices

from app.backend.update_core import ReleaseInfo, detect_platform_key, resolve_available_release
from bao import __version__

_F = TypeVar("_F", bound=Callable[..., object])


def _typed_slot(
    *types: type[object] | str,
    name: str | None = None,
    result: type[object] | str | None = None,
) -> Callable[[_F], _F]:
    if name is None and result is None:
        slot_decorator = Slot(*types)
    elif result is None:
        slot_decorator = Slot(*types, name=name)
    elif name is None:
        slot_decorator = Slot(*types, result=result)
    else:
        slot_decorator = Slot(*types, name=name, result=result)
    return cast(Callable[[_F], _F], slot_decorator)


class UpdateService(QObject):
    stateChanged: ClassVar[Signal] = Signal(str)
    metadataChanged: ClassVar[Signal] = Signal()
    quitRequested: ClassVar[Signal] = Signal()

    _checkFinished: ClassVar[Signal] = Signal(bool, str, object)
    _installFinished: ClassVar[Signal] = Signal(bool, str)

    class _Runner(Protocol):
        def submit(self, coro: Coroutine[Any, Any, object]) -> object: ...

    def __init__(
        self, runner: _Runner, config_service: QObject, parent: QObject | None = None
    ) -> None:
        super().__init__(parent)
        self._runner: UpdateService._Runner = runner
        self._config_service: QObject = config_service
        self._state: str = "idle"
        self._enabled: bool = True
        self._auto_check: bool = True
        self._channel: str = "stable"
        self._feed_url: str = ""
        self._latest_version: str = ""
        self._notes_markdown: str = ""
        self._error_message: str = ""
        self._release: ReleaseInfo | None = None
        self._auto_check_done: bool = False
        self._show_check_errors: bool = False

        _ = self._checkFinished.connect(self._handle_check_finished)
        _ = self._installFinished.connect(self._handle_install_finished)

    @Property(str, notify=metadataChanged)
    def currentVersion(self) -> str:
        return __version__

    @Property(str, notify=stateChanged)
    def state(self) -> str:
        return self._state

    @Property(str, notify=metadataChanged)
    def latestVersion(self) -> str:
        return self._latest_version

    @Property(str, notify=metadataChanged)
    def notesMarkdown(self) -> str:
        return self._notes_markdown

    @Property(str, notify=metadataChanged)
    def errorMessage(self) -> str:
        return self._error_message

    @_typed_slot()
    def reloadConfig(self) -> None:
        update_cfg = self._config_value("ui.update", {})
        self._enabled = bool(update_cfg.get("enabled", True))
        self._auto_check = bool(update_cfg.get("autoCheck", True))
        channel = update_cfg.get("channel", "stable")
        self._channel = channel if isinstance(channel, str) and channel else "stable"
        feed_url = update_cfg.get("feedUrl", "")
        self._feed_url = feed_url if isinstance(feed_url, str) else ""
        self.metadataChanged.emit()
        if self._enabled and self._auto_check and not self._auto_check_done:
            self._auto_check_done = True
            self._start_check(show_errors=False)

    @_typed_slot(name="checkForUpdates")
    def check_for_updates(self) -> None:
        self._start_check(show_errors=True)

    def _start_check(self, *, show_errors: bool) -> None:
        if not self._enabled:
            return
        if not self._feed_url:
            if show_errors:
                self._set_error("Update feed URL is not configured.")
            else:
                self._error_message = ""
                self._set_state("idle")
                self.metadataChanged.emit()
            return
        if self._state in {"checking", "downloading", "installing"}:
            return
        self._show_check_errors = show_errors
        self._clear_release_details(keep_error=False, emit=False)
        self._set_state("checking")
        _ = self._runner.submit(self._check_async())

    @_typed_slot(name="installUpdate")
    def install_update(self) -> None:
        if self._release is None or self._state != "available":
            return
        self._set_state("downloading")
        self._error_message = ""
        self.metadataChanged.emit()
        _ = self._runner.submit(self._install_async())

    async def _check_async(self) -> None:
        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=15.0) as client:
                response = await client.get(self._feed_url, headers={"Accept": "application/json"})
                if response.status_code == 404:
                    if self._show_check_errors:
                        self._checkFinished.emit(
                            False,
                            "Update feed is not published yet (desktop-update.json returned 404).",
                            None,
                        )
                    else:
                        self._checkFinished.emit(True, "", None)
                    return
                _ = response.raise_for_status()
                feed = cast(dict[str, object], response.json())
            if not isinstance(feed, dict):
                raise ValueError("Update feed must be a JSON object")
            platform_key = detect_platform_key(sys.platform, platform.machine())
            if not platform_key:
                self._checkFinished.emit(
                    False, "This platform is not supported for desktop updates.", None
                )
                return
            release = resolve_available_release(
                feed,
                channel=self._channel,
                current_version=__version__,
                platform_key=platform_key,
            )
            self._checkFinished.emit(True, "", release)
        except Exception as exc:
            self._checkFinished.emit(False, str(exc), None)

    async def _install_async(self) -> None:
        try:
            release = self._release
            if release is None:
                raise ValueError("No update is available.")
            workdir = Path(tempfile.mkdtemp(prefix="bao-update-"))
            package_path = await self._download_release(release, workdir)
            if sys.platform.startswith("win"):
                self._launch_windows_installer(package_path, release)
            elif sys.platform == "darwin":
                self._launch_macos_installer(package_path, workdir)
            else:
                raise ValueError("This platform is not supported for in-app installation.")
            self._installFinished.emit(True, "")
        except Exception as exc:
            self._installFinished.emit(False, str(exc))

    async def _download_release(self, release: ReleaseInfo, workdir: Path) -> Path:
        parsed = urlparse(release.asset.url)
        file_name = Path(parsed.path).name or "bao-update.bin"
        package_path = workdir / file_name
        digest = hashlib.sha256()
        async with httpx.AsyncClient(follow_redirects=True, timeout=None) as client:
            async with client.stream("GET", release.asset.url) as response:
                _ = response.raise_for_status()
                with package_path.open("wb") as fh:
                    async for chunk in response.aiter_bytes():
                        if not chunk:
                            continue
                        fh.write(chunk)
                        digest.update(chunk)
        actual_hash = digest.hexdigest()
        if actual_hash.lower() != release.asset.sha256.lower():
            raise ValueError("Downloaded update failed SHA-256 verification.")
        return package_path

    def _launch_windows_installer(self, package_path: Path, release: ReleaseInfo) -> None:
        if not getattr(sys, "frozen", False):
            self._open_release_url(release)
            return
        args = [str(package_path)]
        args.extend(
            release.asset.silent_args or ("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-")
        )
        _ = subprocess.Popen(args, close_fds=True)

    def _launch_macos_installer(self, package_path: Path, workdir: Path) -> None:
        target_app = self._current_app_bundle()
        if target_app is None or package_path.suffix.lower() != ".zip":
            self._open_release_url(self._release)
            return
        staged_root = workdir / "staged"
        staged_root.mkdir(parents=True, exist_ok=True)
        _ = subprocess.run(
            ["/usr/bin/ditto", "-x", "-k", str(package_path), str(staged_root)], check=True
        )
        staged_app = next((path for path in staged_root.iterdir() if path.suffix == ".app"), None)
        if staged_app is None:
            raise ValueError("Update archive does not contain an app bundle.")
        script_path = workdir / "apply_update.sh"
        script_text = self._build_macos_apply_script(
            pid=os.getpid(),
            target_app=target_app,
            staged_app=staged_app,
            workdir=workdir,
        )
        script_path.write_text(script_text, encoding="utf-8")
        _ = script_path.chmod(0o755)
        _ = subprocess.Popen(
            ["/bin/bash", str(script_path)], close_fds=True, start_new_session=True
        )

    def _build_macos_apply_script(
        self,
        *,
        pid: int,
        target_app: Path,
        staged_app: Path,
        workdir: Path,
    ) -> str:
        q = shlex.quote
        return f"""#!/usr/bin/env bash
set -euo pipefail
PID={pid}
TARGET_APP={q(str(target_app))}
STAGED_APP={q(str(staged_app))}
WORKDIR={q(str(workdir))}

while kill -0 \"$PID\" 2>/dev/null; do
  sleep 0.3
done

TMP_APP=\"${{TARGET_APP}}.new\"
BAK_APP=\"${{TARGET_APP}}.bak\"
rm -rf \"$TMP_APP\" \"$BAK_APP\"
/usr/bin/ditto \"$STAGED_APP\" \"$TMP_APP\"
if [[ -d \"$TARGET_APP\" ]]; then
  mv \"$TARGET_APP\" \"$BAK_APP\"
fi
mv \"$TMP_APP\" \"$TARGET_APP\"
open \"$TARGET_APP\"
( sleep 5; rm -rf \"$WORKDIR\" ) >/dev/null 2>&1 &
"""

    def _current_app_bundle(self) -> Path | None:
        if not getattr(sys, "frozen", False):
            return None
        exe_path = Path(sys.executable).resolve()
        if exe_path.suffix == ".app":
            return exe_path
        parents = list(exe_path.parents)
        for parent in parents:
            if parent.suffix == ".app":
                return parent
        return None

    def _handle_check_finished(self, ok: bool, error: str, release: object) -> None:
        if not ok:
            if self._show_check_errors:
                self._set_error(error or "Failed to check for updates.")
            else:
                self._error_message = ""
                self._set_state("idle")
                self.metadataChanged.emit()
            return
        if not isinstance(release, ReleaseInfo):
            self._set_release(None)
            self._error_message = ""
            self._set_state("up_to_date")
            self.metadataChanged.emit()
            return
        self._set_release(release)
        self._error_message = ""
        self._set_state("available")
        self.metadataChanged.emit()

    def _handle_install_finished(self, ok: bool, error: str) -> None:
        if not ok:
            self._set_error(error or "Failed to install update.")
            return
        self._set_state("installing")
        self.quitRequested.emit()

    def _set_error(self, message: str) -> None:
        self._error_message = message
        self._set_state("error")
        self.metadataChanged.emit()

    def _set_state(self, value: str) -> None:
        if self._state == value:
            return
        self._state = value
        self.stateChanged.emit(self._state)

    def _clear_release_details(self, *, keep_error: bool, emit: bool = True) -> None:
        self._set_release(None)
        if not keep_error:
            self._error_message = ""
        if emit:
            self.metadataChanged.emit()

    def _set_release(self, release: ReleaseInfo | None) -> None:
        self._release = release
        self._latest_version = release.version if release is not None else ""
        self._notes_markdown = release.notes_markdown if release is not None else ""

    def _open_release_url(self, release: ReleaseInfo | None) -> None:
        if release is None:
            return
        url = release.release_url or release.asset.url
        if url:
            _ = QDesktopServices.openUrl(QUrl(url))

    def _config_value(self, dotpath: str, default: object) -> Any:
        getter = getattr(self._config_service, "get", None)
        if callable(getter):
            return getter(dotpath, default)
        return default


class UpdateBridge(QObject):
    checkRequested: ClassVar[Signal] = Signal()
    installRequested: ClassVar[Signal] = Signal()
    reloadRequested: ClassVar[Signal] = Signal()
