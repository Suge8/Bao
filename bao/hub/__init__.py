from __future__ import annotations

from importlib import import_module
from typing import Any

_EXPORTS: dict[str, tuple[str, str]] = {
    "HubClearActiveSessionRequest": ("._control_types", "HubClearActiveSessionRequest"),
    "HubControl": (".control", "HubControl"),
    "HubCreateSessionRequest": ("._control_types", "HubCreateSessionRequest"),
    "HubDeleteRequest": ("._control_types", "HubDeleteRequest"),
    "HubDirectory": (".directory", "HubDirectory"),
    "HubLocalPorts": (".local", "HubLocalPorts"),
    "HubPersistMessageRequest": (".runtime", "HubPersistMessageRequest"),
    "HubRunningStateRequest": (".runtime", "HubRunningStateRequest"),
    "HubRuntimePort": (".runtime", "HubRuntimePort"),
    "HubSendRequest": ("._control_types", "HubSendRequest"),
    "HubSeenRequest": (".runtime", "HubSeenRequest"),
    "HubSetActiveSessionRequest": ("._control_types", "HubSetActiveSessionRequest"),
    "HubSpawnChildRequest": ("._control_types", "HubSpawnChildRequest"),
    "HubStopRequest": ("._control_types", "HubStopRequest"),
    "HubTaskControl": (".tasks", "HubTaskControl"),
    "HubTaskDirectory": (".tasks", "HubTaskDirectory"),
    "HubUserMessageStatusRequest": (".runtime", "HubUserMessageStatusRequest"),
    "IdentityLinkRecord": ("._session_directory_models", "IdentityLinkRecord"),
    "IdentityMemberRecord": ("._session_directory_models", "IdentityMemberRecord"),
    "SessionBindingRecord": ("._session_directory_models", "SessionBindingRecord"),
    "SessionPreferenceRecord": ("._session_directory_models", "SessionPreferenceRecord"),
    "SessionRecord": ("._session_directory_models", "SessionRecord"),
    "TranscriptPage": ("._directory_models", "TranscriptPage"),
    "TranscriptReadRequest": ("._directory_models", "TranscriptReadRequest"),
    "build_binding_key": ("._session_directory_identity", "build_binding_key"),
    "build_session_ref": ("._session_directory_identity", "build_session_ref"),
    "decode_transcript_cursor": ("._directory_models", "decode_transcript_cursor"),
    "encode_transcript_cursor": ("._directory_models", "encode_transcript_cursor"),
    "local_hub_control": (".control", "local_hub_control"),
    "open_local_hub_ports": (".local", "open_local_hub_ports"),
}

__all__ = sorted(_EXPORTS)


def __getattr__(name: str) -> Any:
    target = _EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attr_name = target
    module = import_module(module_name, __name__)
    value = getattr(module, attr_name)
    globals()[name] = value
    return value
