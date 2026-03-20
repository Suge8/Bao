from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

from bao.hub._channel_binding import ChannelBindingStore
from bao.hub._route_index import SessionRouteIndex
from bao.hub._session_directory_identity import build_binding_key

RouteResolutionSource = Literal["explicit", "route_index", "channel_binding", "default_profile"]
_EXPLICIT_REASON = "explicit_profile_id"
_ROUTE_INDEX_REASON = "session_key_route_index"
_CHANNEL_BINDING_REASON = "origin_channel_binding"
_DEFAULT_REASON = "registry_default_profile"
_THREAD_METADATA_KEYS = ("thread_id", "topic_id", "message_thread_id", "thread_ts")
_ACCOUNT_METADATA_KEYS = ("account_id", "bot_id")
_PEER_METADATA_KEYS = ("peer_id",)


@dataclass(frozen=True, slots=True)
class SessionOrigin:
    channel: str = ""
    account_id: str = ""
    peer_id: str = ""
    thread_id: str = ""

    @classmethod
    def create(
        cls,
        *,
        channel: object,
        chat_id: object,
        metadata: Mapping[str, Any] | None = None,
    ) -> "SessionOrigin":
        payload = _metadata_mapping(metadata)
        return cls(
            channel=_normalize_channel(channel),
            account_id=_first_text(payload, _ACCOUNT_METADATA_KEYS),
            peer_id=_first_text(payload, _PEER_METADATA_KEYS, fallback=chat_id),
            thread_id=_first_text(payload, _THREAD_METADATA_KEYS),
        )

    def binding_key(self) -> str:
        if self.channel == "hub" and self.peer_id == "direct":
            return ""
        return build_binding_key(
            channel=self.channel,
            account_id=self.account_id,
            peer_id=self.peer_id,
            thread_id=self.thread_id,
        )

    def as_snapshot(self) -> dict[str, str]:
        return {
            "channel": self.channel,
            "account_id": self.account_id,
            "peer_id": self.peer_id,
            "thread_id": self.thread_id,
        }


@dataclass(frozen=True, slots=True)
class RouteResolutionResult:
    profile_id: str
    source: RouteResolutionSource
    session_key: str = ""
    origin: SessionOrigin = SessionOrigin()
    reason: str = ""

    def as_snapshot(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "source": self.source,
            "session_key": self.session_key,
            "reason": self.reason,
            "origin": self.origin.as_snapshot(),
            "origin_key": self.origin.binding_key(),
        }


class HubRouteResolver:
    def __init__(
        self,
        *,
        route_index: SessionRouteIndex,
        channel_bindings: ChannelBindingStore,
        default_profile_id: object = "",
    ) -> None:
        self._route_index = route_index
        self._channel_bindings = channel_bindings
        self._default_profile_id = _normalize_profile_id(default_profile_id)

    def resolve(
        self,
        *,
        explicit_profile_id: object,
        session_key: object,
        origin: SessionOrigin,
    ) -> RouteResolutionResult:
        explicit = _normalize_profile_id(explicit_profile_id)
        normalized_session_key = _normalize_session_key(session_key)
        if explicit:
            return RouteResolutionResult(
                explicit,
                "explicit",
                normalized_session_key,
                origin,
                _EXPLICIT_REASON,
            )
        if normalized_session_key:
            mapped = self._route_index.resolve(normalized_session_key)
            if mapped:
                return RouteResolutionResult(
                    mapped,
                    "route_index",
                    normalized_session_key,
                    origin,
                    _ROUTE_INDEX_REASON,
                )
        mapped = self._channel_bindings.resolve(origin.binding_key())
        if mapped:
            return RouteResolutionResult(
                mapped,
                "channel_binding",
                normalized_session_key,
                origin,
                _CHANNEL_BINDING_REASON,
            )
        return RouteResolutionResult(
            self._default_profile_id,
            "default_profile",
            normalized_session_key,
            origin,
            _DEFAULT_REASON,
        )

    def remember(
        self,
        *,
        session_key: object,
        origin: SessionOrigin,
        profile_id: object,
    ) -> None:
        normalized_profile = _normalize_profile_id(profile_id)
        if not normalized_profile:
            return
        self._route_index.bind(session_key, normalized_profile)
        origin_key = origin.binding_key()
        if origin_key:
            self._channel_bindings.bind(origin_key, normalized_profile)

    def unbind(self, session_key: object) -> None:
        self._route_index.unbind(session_key)


def _metadata_mapping(metadata: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(metadata, Mapping):
        return {}
    return dict(metadata)


def _first_text(
    payload: Mapping[str, Any],
    keys: tuple[str, ...],
    *,
    fallback: object = "",
) -> str:
    for key in keys:
        normalized = _normalize_text(payload.get(key))
        if normalized:
            return normalized
    return _normalize_text(fallback)


def _normalize_channel(value: object) -> str:
    normalized = _normalize_text(value)
    return normalized.lower()


def _normalize_profile_id(value: object) -> str:
    return _normalize_text(value)


def _normalize_session_key(value: object) -> str:
    return _normalize_text(value)


def _normalize_text(value: object) -> str:
    if isinstance(value, bool):
        return ""
    if isinstance(value, int):
        return str(value)
    if not isinstance(value, str):
        return ""
    return value.strip()
