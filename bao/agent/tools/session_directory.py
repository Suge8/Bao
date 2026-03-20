from __future__ import annotations

from typing import Any, Awaitable, Callable
from uuid import uuid4

from bao.agent._session_handoff import (
    SESSION_HANDOFF_REQUEST_EVENT_TYPE,
    SessionHandoffRequest,
    conversation_label,
)
from bao.agent.tools._delivery_errors import _SESSION_DISCOVERY_HINT, delivery_error_result
from bao.agent.tools._session_directory_read_tools import (
    SessionDefaultTool,
    SessionLookupTool,
    SessionRecentTool,
    SessionResolveTool,
    SessionStatusTool,
    SessionTranscriptTool,
)
from bao.agent.tools._session_directory_tool_base import (
    SessionDirectoryToolBase,
    SessionDirectoryToolContext,
    _normalize_text,
)
from bao.bus.events import ControlEvent

__all__ = [
    "SendToSessionTool",
    "SessionDefaultTool",
    "SessionDirectoryToolContext",
    "SessionLookupTool",
    "SessionRecentTool",
    "SessionResolveTool",
    "SessionStatusTool",
    "SessionTranscriptTool",
]

_HANDOFF_ID_PREVIEW_CHARS = 60


class SendToSessionTool(SessionDirectoryToolBase):
    def __init__(
        self,
        directory: Any,
        publish_control: Callable[[ControlEvent], Awaitable[None]],
    ) -> None:
        super().__init__(directory)
        self._publish_control = publish_control

    @property
    def name(self) -> str:
        return "send_to_session"

    @property
    def description(self) -> str:
        return (
            "Hand off work to another Bao-managed session. Runtime will announce receipt on the "
            "target side, let that session process the request, and route the result back here. "
            "Resolve the target with session_lookup/session_default/session_resolve first when needed."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "Text to hand off."},
                "session_key": {"type": "string", "description": "Explicit target session key."},
                "session_ref": {"type": "string", "description": "Stable target session ref."},
                "media": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional list of local file paths to attach.",
                },
            },
        }

    async def execute(self, **kwargs: Any) -> str | Any:
        route = self._route.get()
        content = kwargs.get("content", "")
        if not isinstance(content, str):
            return delivery_error_result(code="invalid_params", message="Error: content must be a string.")
        media = kwargs.get("media")
        if media is not None and not isinstance(media, list):
            return delivery_error_result(code="invalid_params", message="Error: media must be a list of file paths.")
        media_list = _normalize_media_list(media)
        if not content.strip() and not media_list:
            return delivery_error_result(code="invalid_params", message="Error: send_to_session requires content or media.")
        if not _normalize_text(route.session_key):
            return delivery_error_result(
                code="delivery_failed",
                message="Error: send_to_session requires an active source session route.",
            )

        target_session_key, resolved = self._resolve_target(
            session_key=kwargs.get("session_key"),
            session_ref=kwargs.get("session_ref"),
        )
        if not target_session_key:
            return delivery_error_result(
                code="invalid_params",
                message="Error: send_to_session requires session_key or a resolvable session_ref.",
                guidance=_SESSION_DISCOVERY_HINT,
            )
        if target_session_key == _normalize_text(route.session_key):
            return delivery_error_result(
                code="invalid_params",
                message="Error: send_to_session cannot target the current session. Use the normal reply path.",
            )

        handoff_request = self._build_handoff_request(
            route=route,
            target_session_key=target_session_key,
            resolved=resolved,
            session_ref=kwargs.get("session_ref"),
            content=content,
            media_list=media_list,
        )
        route_error = _validate_handoff_target_route(handoff_request)
        if route_error is not None:
            return route_error
        try:
            await self._publish_control(
                ControlEvent(
                    kind=SESSION_HANDOFF_REQUEST_EVENT_TYPE,
                    payload=handoff_request.as_payload(),
                    session_key=target_session_key,
                    origin_channel=route.channel or "hub",
                    origin_chat_id=route.chat_id or "direct",
                    source="send_to_session",
                )
            )
        except Exception as exc:
            return delivery_error_result(
                code="delivery_failed",
                message=f"Error sending to session: {exc}",
            )
        target_label = conversation_label(
            explicit_label=handoff_request.target_label,
            channel=handoff_request.target_channel or _channel_from_session_key(target_session_key),
            lang="en",
        )
        return f"Session handoff queued for {target_label}: {_preview_content(content, media_count=len(media_list))}"

    def _build_handoff_request(
        self,
        *,
        route: Any,
        target_session_key: str,
        resolved: dict[str, Any],
        session_ref: object,
        content: str,
        media_list: list[str],
    ) -> SessionHandoffRequest:
        target_delivery = self._resolve_target_delivery(
            session_key=target_session_key,
            session_ref=session_ref,
        )
        source_session_key = _normalize_text(route.session_key)
        target_channel = _resolve_target_channel(
            target_delivery=target_delivery,
            resolved=resolved,
            session_key=target_session_key,
        )
        return SessionHandoffRequest(
            handoff_id=uuid4().hex[:12],
            source_session_key=source_session_key,
            source_channel=route.channel or "hub",
            source_chat_id=route.chat_id or "direct",
            source_metadata=_source_handoff_metadata(route),
            source_label=self._resolve_session_title(session_key=source_session_key),
            target_session_key=target_session_key,
            target_session_ref=_normalize_text(resolved.get("session_ref")),
            target_channel=target_channel,
            target_chat_id=_normalize_text(target_delivery.get("chat_id")),
            target_metadata=dict(target_delivery.get("metadata") or {}),
            target_label=self._resolve_session_title(session_key=target_session_key, resolved=resolved),
            content=content,
            media=tuple(media_list),
        )

    def _resolve_target_delivery(self, *, session_key: str, session_ref: object) -> dict[str, Any]:
        normalized_ref = _normalize_text(session_ref)
        if not normalized_ref:
            record = self._call_directory("get_session_directory_record", key=session_key)
            if isinstance(record, dict):
                normalized_ref = _normalize_text(record.get("session_ref"))
        if not normalized_ref:
            return {}
        target = self._call_directory("resolve_delivery_target", session_ref=normalized_ref)
        return dict(target) if isinstance(target, dict) else {}

    def _resolve_session_title(
        self,
        *,
        session_key: str,
        resolved: dict[str, Any] | None = None,
    ) -> str:
        entry = self._call_directory("get_session", key=session_key)
        record = self._call_directory("get_session_directory_record", key=session_key)
        for payload in (entry, resolved or {}, record):
            title = _session_title_from_payload(payload)
            if title:
                return title
        return ""


def _normalize_media_list(media: object) -> list[str]:
    if not isinstance(media, list):
        return []
    return [item.strip() for item in media if isinstance(item, str) and item.strip()]


def _source_handoff_metadata(route: Any) -> dict[str, Any]:
    metadata = dict(route.reply_metadata or {})
    message_id = getattr(route, "message_id", None)
    if isinstance(message_id, str) and message_id.strip():
        metadata["message_id"] = message_id.strip()
    return metadata


def _preview_content(content: str, *, media_count: int = 0) -> str:
    preview = content[:_HANDOFF_ID_PREVIEW_CHARS].replace("\n", " ").replace("\r", "")
    if len(content) > _HANDOFF_ID_PREVIEW_CHARS:
        preview += "..."
    if preview and media_count > 0:
        return f"{preview} [+{media_count} media]"
    if preview:
        return preview
    return "[media only]" if media_count > 0 else "…"


def _session_title_from_payload(payload: object) -> str:
    if not isinstance(payload, dict):
        return ""
    view = payload.get("view")
    if isinstance(view, dict):
        title = _normalize_text(view.get("title"))
        if title:
            return title
    return _normalize_text(payload.get("title"))


def _channel_from_session_key(session_key: str) -> str:
    return _normalize_text(session_key.partition(":")[0]).lower()


def _resolve_target_channel(
    *,
    target_delivery: dict[str, Any],
    resolved: dict[str, Any],
    session_key: str,
) -> str:
    return (
        _normalize_text(target_delivery.get("channel"))
        or _normalize_text(resolved.get("channel"))
        or _channel_from_session_key(session_key)
    )


def _validate_handoff_target_route(request: SessionHandoffRequest) -> Any | None:
    if request.target_channel and request.target_chat_id:
        return None
    return delivery_error_result(
        code="delivery_failed",
        message=(
            "Error: target session does not have a deliverable external route yet. "
            "Resolve an observed session with a real channel/chat_id first."
        ),
        guidance=_SESSION_DISCOVERY_HINT,
    )
