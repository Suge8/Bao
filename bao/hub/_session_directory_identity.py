from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from typing import Literal

from ._normalization import normalize_channel, normalize_text

SESSION_REF_PREFIX = "sess"
SESSION_REF_HASH_LENGTH = 12

SessionAvailability = Literal["active", "dormant", "unreachable", "archived", "deleted"]
SessionBindingSource = Literal["observed", "explicit", "imported", "migrated"]
SessionPreferenceReason = Literal["explicit", "binding", "recent_success"]
IdentityConfidence = Literal["explicit", "candidate"]


def build_binding_key(
    *,
    channel: object,
    peer_id: object,
    account_id: object = "",
    thread_id: object = "",
) -> str:
    normalized_channel = normalize_channel(channel)
    normalized_peer = normalize_text(peer_id)
    if not normalized_channel or not normalized_peer:
        return ""
    parts = [f"channel={normalized_channel}"]
    normalized_account = normalize_text(account_id)
    if normalized_account:
        parts.append(f"account={normalized_account}")
    parts.append(f"peer={normalized_peer}")
    normalized_thread = normalize_text(thread_id)
    if normalized_thread:
        parts.append(f"thread={normalized_thread}")
    return "|".join(parts)


def build_session_ref(
    *,
    session_key: object,
    channel: object,
    account_id: object = "",
    peer_id: object = "",
    thread_id: object = "",
) -> str:
    payload = _session_ref_payload(
        session_key=session_key,
        channel=channel,
        account_id=account_id,
        peer_id=peer_id,
        thread_id=thread_id,
    )
    if payload is None:
        return ""
    raw = json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("utf-8")
    digest = hashlib.sha1(raw).hexdigest()[:SESSION_REF_HASH_LENGTH]
    return f"{SESSION_REF_PREFIX}_{digest}"


def normalize_session_availability(value: object) -> SessionAvailability:
    normalized = normalize_text(value).lower()
    if normalized in {"active", "unreachable", "archived", "deleted"}:
        return normalized
    return "dormant"


def normalize_binding_source(value: object) -> SessionBindingSource:
    normalized = normalize_text(value).lower()
    if normalized in {"explicit", "imported", "migrated"}:
        return normalized
    return "observed"


def normalize_preference_reason(value: object) -> SessionPreferenceReason:
    normalized = normalize_text(value).lower()
    if normalized in {"binding", "recent_success"}:
        return normalized
    return "explicit"


def normalize_identity_confidence(value: object) -> IdentityConfidence:
    normalized = normalize_text(value).lower()
    if normalized == "candidate":
        return "candidate"
    return "explicit"


def normalize_preview_items(values: Iterable[object] | None) -> tuple[str, ...]:
    if values is None:
        return ()
    normalized = [item for item in (normalize_text(value) for value in values) if item]
    return tuple(normalized)


def normalize_identity_member_mapping(value: Mapping[str, object]) -> dict[str, str]:
    return {
        "channel": normalize_channel(value.get("channel")),
        "peer_id": normalize_text(value.get("peer_id")),
        "account_id": normalize_text(value.get("account_id")),
        "thread_id": normalize_text(value.get("thread_id")),
        "session_ref": normalize_text(value.get("session_ref")),
    }


def _session_ref_payload(
    *,
    session_key: object,
    channel: object,
    account_id: object = "",
    peer_id: object = "",
    thread_id: object = "",
) -> dict[str, str] | None:
    normalized_session_key = normalize_text(session_key)
    normalized_channel = normalize_channel(channel)
    normalized_account = normalize_text(account_id)
    normalized_peer = normalize_text(peer_id)
    normalized_thread = normalize_text(thread_id)
    if normalized_channel and normalized_peer:
        return {
            "channel": normalized_channel,
            "account_id": normalized_account,
            "peer_id": normalized_peer,
            "thread_id": normalized_thread,
            "session_key": normalized_session_key,
        }
    if normalized_session_key:
        return {"session_key": normalized_session_key}
    return None
