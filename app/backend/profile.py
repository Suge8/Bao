from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, ClassVar

from PySide6.QtCore import Property, QObject, Signal, Slot

from bao.profile import (
    ProfileContext,
    ProfileRegistry,
    create_profile,
    delete_profile,
    load_active_profile_snapshot,
    profile_context_to_dict,
    rename_profile,
    set_active_profile,
    update_profile,
)


class ProfileService(QObject):
    profilesChanged: ClassVar[Signal] = Signal()
    activeProfileChanged: ClassVar[Signal] = Signal()
    errorChanged: ClassVar[Signal] = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._shared_workspace_path = ""
        self._registry: ProfileRegistry | None = None
        self._active_context: ProfileContext | None = None
        self._profile_rows: list[dict[str, Any]] = []
        self._last_error = ""

    @Property(list, notify=profilesChanged)
    def profiles(self) -> list[dict[str, Any]]:
        return [dict(item) for item in self._profile_rows]

    @Property(dict, notify=activeProfileChanged)
    def activeProfile(self) -> dict[str, Any]:
        return self._active_profile_row()

    @Property(dict, notify=activeProfileChanged)
    def activeProfileContext(self) -> dict[str, Any]:
        return profile_context_to_dict(self._active_context)

    @Property(str, notify=activeProfileChanged)
    def activeProfileId(self) -> str:
        context = self._active_context
        return context.profile_id if context is not None else ""

    @Property(str, notify=profilesChanged)
    def sharedWorkspacePath(self) -> str:
        return self._shared_workspace_path

    @Property(str, notify=errorChanged)
    def lastError(self) -> str:
        return self._last_error

    def _shared_workspace(self) -> Path:
        return Path(self._shared_workspace_path).expanduser()

    def _run_workspace_action(
        self,
        action: Callable[[Path], tuple[ProfileRegistry, ProfileContext]],
    ) -> None:
        if not self._shared_workspace_path:
            return
        self._run_action(self._shared_workspace(), action)

    def _run_profile_action(
        self,
        profile_id: str,
        action: Callable[[Path, str], tuple[ProfileRegistry, ProfileContext]],
    ) -> None:
        normalized_id = profile_id.strip()
        if not normalized_id:
            return
        self._run_workspace_action(
            lambda shared_workspace: action(shared_workspace, normalized_id),
        )

    @Slot(str)
    def refreshFromWorkspace(self, workspace_path: str) -> None:
        raw = workspace_path.strip()
        if not raw:
            return
        self._run_action(
            Path(raw).expanduser(),
            lambda shared_workspace: load_active_profile_snapshot(shared_workspace=shared_workspace),
        )

    @Slot(str)
    def activateProfile(self, profile_id: str) -> None:
        self._run_profile_action(
            profile_id,
            lambda shared_workspace, normalized_id: set_active_profile(
                normalized_id,
                shared_workspace=shared_workspace,
            ),
        )

    @Slot(str)
    def createProfile(self, display_name: str) -> None:
        self._run_workspace_action(
            lambda shared_workspace: create_profile(
                display_name,
                shared_workspace=shared_workspace,
                activate=True,
            ),
        )

    @Slot(str)
    def deleteProfile(self, profile_id: str) -> None:
        self._run_profile_action(
            profile_id,
            lambda shared_workspace, normalized_id: delete_profile(
                normalized_id,
                shared_workspace=shared_workspace,
            ),
        )

    @Slot(str, str)
    def renameProfile(self, profile_id: str, display_name: str) -> None:
        self._run_profile_action(
            profile_id,
            lambda shared_workspace, normalized_id: rename_profile(
                normalized_id,
                display_name,
                shared_workspace=shared_workspace,
            ),
        )

    @Slot(str, str, str)
    def updateProfile(self, profile_id: str, display_name: str, storage_key: str) -> None:
        self._run_profile_action(
            profile_id,
            lambda shared_workspace, normalized_id: update_profile(
                normalized_id,
                display_name=display_name,
                storage_key=storage_key,
                shared_workspace=shared_workspace,
            ),
        )

    def _project_profiles(
        self,
        registry: ProfileRegistry,
        context: ProfileContext,
    ) -> list[dict[str, Any]]:
        active_id = context.profile_id
        return [
            {
                "id": spec.id,
                "displayName": spec.display_name,
                "storageKey": spec.storage_key,
                "avatarKey": spec.avatar_key,
                "canDelete": spec.id != registry.default_profile_id,
                "enabled": bool(spec.enabled),
                "createdAt": spec.created_at,
                "isActive": spec.id == active_id,
            }
            for spec in registry.profiles
        ]

    def _active_profile_row(
        self,
        *,
        rows: list[dict[str, Any]] | None = None,
        context: ProfileContext | None = None,
    ) -> dict[str, Any]:
        active_context = self._active_context if context is None else context
        active_id = active_context.profile_id if active_context is not None else ""
        for item in self._profile_rows if rows is None else rows:
            if str(item.get("id", "")) == active_id:
                return dict(item)
        return {}

    def _run_action(
        self,
        shared_workspace: Path,
        action: Callable[[Path], tuple[ProfileRegistry, ProfileContext]],
    ) -> None:
        try:
            registry, context = action(shared_workspace)
        except Exception as exc:
            self._set_error(str(exc))
            return
        self._set_error("")
        self._apply_state(registry, context, shared_workspace=shared_workspace)

    def _apply_state(
        self,
        registry: ProfileRegistry,
        context: ProfileContext,
        *,
        shared_workspace: Path,
    ) -> None:
        previous_rows = self._profile_rows
        previous_context = self._active_context
        previous_active_profile = self._active_profile_row(rows=previous_rows, context=previous_context)
        workspace_changed = self._shared_workspace_path != str(shared_workspace)
        profile_rows = self._project_profiles(registry, context)
        active_profile = self._active_profile_row(rows=profile_rows, context=context)
        profiles_changed = workspace_changed or registry != self._registry or profile_rows != previous_rows
        active_changed = context != previous_context or active_profile != previous_active_profile
        self._shared_workspace_path = str(shared_workspace)
        self._registry = registry
        self._active_context = context
        self._profile_rows = profile_rows
        if profiles_changed:
            self.profilesChanged.emit()
        if active_changed:
            self.activeProfileChanged.emit()

    def _set_error(self, message: str) -> None:
        if self._last_error == message:
            return
        self._last_error = message
        self.errorChanged.emit()
