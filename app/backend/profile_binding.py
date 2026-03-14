from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import QTimer

from bao.profile import ProfileContext, profile_context_from_mapping, profile_context_to_dict


class DesktopProfileCoordinator:
    def __init__(
        self,
        *,
        config_service: Any,
        profile_service: Any,
        chat_service: Any,
        session_service: Any,
        memory_service: Any,
        cron_service: Any,
        heartbeat_service: Any,
        skills_service: Any,
        schedule_call: Callable[[int, Callable[[], None]], None] = QTimer.singleShot,
        default_workspace: str = "~/.bao/workspace",
    ) -> None:
        self._config_service = config_service
        self._profile_service = profile_service
        self._chat_service = chat_service
        self._session_service = session_service
        self._memory_service = memory_service
        self._cron_service = cron_service
        self._heartbeat_service = heartbeat_service
        self._skills_service = skills_service
        self._schedule_call = schedule_call
        self._default_workspace = default_workspace
        self._applied_context: ProfileContext | None = None
        self._resume_gateway_key: tuple[str, str, str, str] | None = None

    def refresh_from_config(self) -> None:
        workspace_path = self._workspace_path_from_config()
        self._profile_service.refreshFromWorkspace(workspace_path)
        self._skills_service.setWorkspacePath(workspace_path)

    def apply_active_profile(self) -> None:
        context = self._active_profile_context()
        self._chat_service.setProfileContext(profile_context_to_dict(context))
        if context is None:
            self._applied_context = None
            self._resume_gateway_key = None
            return

        previous = self._applied_context
        self._rebind_local_services(context, previous)
        self._sync_gateway_transition(context, previous)
        self._applied_context = context

    def restart_gateway_if_ready(self, _manager: object) -> None:
        pending = self._resume_gateway_key
        if pending is None:
            return
        if self._runtime_context_key(self._active_profile_context()) != pending:
            return
        self._resume_gateway_key = None
        self._schedule_call(0, self._chat_service.start)

    def _rebind_local_services(
        self,
        context: ProfileContext,
        previous: ProfileContext | None,
    ) -> None:
        if previous is None or context.state_root != previous.state_root:
            self._session_service.bootstrapStorageRoot(str(context.state_root))
            self._memory_service.bootstrapStorageRoot(str(context.state_root))
        if previous is None or context.cron_store_path != previous.cron_store_path:
            self._cron_service.setLocalStorePath(str(context.cron_store_path))
        if previous is None or context.heartbeat_file != previous.heartbeat_file:
            self._heartbeat_service.setLocalHeartbeatFilePath(str(context.heartbeat_file))

        self._cron_service.setProfileInfo(context.profile_id, context.display_name)
        self._heartbeat_service.setProfileInfo(context.profile_id, context.display_name)

    def _sync_gateway_transition(
        self,
        context: ProfileContext,
        previous: ProfileContext | None,
    ) -> None:
        if self._runtime_context_key(context) == self._runtime_context_key(previous):
            return
        if not self._gateway_running() and self._resume_gateway_key is None:
            return
        self._resume_gateway_key = self._runtime_context_key(context)
        if self._gateway_running():
            self._chat_service.stop()

    def _runtime_context_key(
        self,
        context: ProfileContext | None,
    ) -> tuple[str, str, str, str] | None:
        if context is None:
            return None
        return (
            context.profile_id,
            str(context.state_root),
            str(context.cron_store_path),
            str(context.heartbeat_file),
        )

    def _active_profile_context(self) -> ProfileContext | None:
        return profile_context_from_mapping(getattr(self._profile_service, "activeProfileContext", None))

    def _gateway_running(self) -> bool:
        state = str(getattr(self._chat_service, "state", "") or "")
        return state in {"running", "starting"}

    def _workspace_path_from_config(self) -> str:
        workspace_value = self._config_service.get("agents.defaults.workspace", self._default_workspace)
        workspace_raw = workspace_value if isinstance(workspace_value, str) else self._default_workspace
        return str(Path(workspace_raw).expanduser())
