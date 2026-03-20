from __future__ import annotations

import re
from typing import Any

from ._normalization import normalize_channel, normalize_text
from ._session_directory_models import IdentityLinkRecord, SessionPreferenceRecord, SessionRecord

_DEFAULT_RECENT_LIMIT = 8
_DEFAULT_LOOKUP_LIMIT = 8
_QUERY_SPLIT_RE = re.compile(r"[^0-9A-Za-z\u4e00-\u9fff]+")
_DEFAULT_ELIGIBLE_AVAILABILITY = frozenset({"active", "dormant", "unreachable"})
_VISIBLE_AVAILABILITY = frozenset({"active", "dormant", "unreachable", "archived"})
_UNSENDABLE_CHANNELS = frozenset({"desktop", "hub"})


class SessionDirectoryReadPlane:
    def __init__(self, *, session_manager: Any, runtime: Any) -> None:
        self._session_manager = session_manager
        self._runtime = runtime

    def list_recent_sessions(
        self,
        *,
        limit: int | None = None,
        channel: str | None = None,
    ) -> list[dict[str, Any]]:
        records = self._filtered_records(channel=channel, allowed_availability=_VISIBLE_AVAILABILITY)
        target_limit = _normalize_limit(limit, default=_DEFAULT_RECENT_LIMIT)
        return [self._snapshot(record) for record in records[:target_limit]]

    def lookup_sessions(
        self,
        *,
        query: str,
        limit: int | None = None,
        channel: str | None = None,
    ) -> list[dict[str, Any]]:
        normalized_query = normalize_text(query)
        if not normalized_query:
            return []
        target_limit = _normalize_limit(limit, default=_DEFAULT_LOOKUP_LIMIT)
        identity_map = self._identity_map()
        scored: list[tuple[tuple[int, int, str, str], SessionRecord]] = []
        for record in self._filtered_records(channel=channel, allowed_availability=_VISIBLE_AVAILABILITY):
            match = _lookup_match(record, normalized_query, identity_map.get(record.session_ref))
            if match is None:
                continue
            scored.append((match, record))
        scored.sort(key=lambda item: item[0], reverse=True)
        results = [self._snapshot(record) for _score, record in scored[:target_limit]]
        for item in results:
            identity = identity_map.get(str(item.get("session_ref") or ""))
            if identity is not None:
                item["identity_ref"] = identity.identity_ref
        return results

    def get_default_session(
        self,
        *,
        channel: str | None = None,
        scope: str | None = None,
        session_key: str | None = None,
    ) -> dict[str, Any]:
        _ = scope
        candidates = self._filtered_records(channel=channel, allowed_availability=_DEFAULT_ELIGIBLE_AVAILABILITY)
        preference = self._preferred_session_from_preferences(
            candidates,
            channel=channel,
            scope=scope,
        )
        if preference is not None:
            snapshot, matched = preference
            snapshot["default"] = True
            snapshot["reason"] = matched.reason
            snapshot["scope"] = matched.scope
            return snapshot
        preferred_key = normalize_text(session_key)
        if preferred_key:
            preferred = next((record for record in candidates if record.session_key == preferred_key), None)
            if preferred is not None:
                snapshot = self._snapshot(preferred)
                snapshot["default"] = True
                snapshot["reason"] = "current_session"
                return snapshot
        if not candidates:
            return {}
        snapshot = self._snapshot(candidates[0])
        snapshot["default"] = True
        snapshot["reason"] = "most_recent"
        return snapshot

    def resolve_session_ref(self, *, session_ref: str) -> dict[str, Any]:
        record = self._record_by_ref(session_ref)
        if record is None:
            return {}
        snapshot = self._snapshot(record)
        identity = self._identity_map().get(record.session_ref)
        if identity is not None:
            snapshot["identity_ref"] = identity.identity_ref
        return snapshot

    def resolve_delivery_target(self, *, session_ref: str) -> dict[str, Any]:
        record = self._record_by_ref(session_ref)
        if record is None:
            return {}
        return _delivery_target_snapshot(record)

    def _record_by_ref(self, session_ref: str) -> SessionRecord | None:
        normalized_ref = normalize_text(session_ref)
        if not normalized_ref:
            return None
        record = self._runtime.store.get_record_by_ref(normalized_ref)
        if record is None:
            record = next((item for item in self._candidate_records() if item.session_ref == normalized_ref), None)
        return record

    def _filtered_records(
        self,
        *,
        channel: str | None,
        allowed_availability: frozenset[str],
    ) -> list[SessionRecord]:
        normalized_channel = normalize_channel(channel)
        records = [
            record
            for record in self._candidate_records()
            if record.availability in allowed_availability
            and (not normalized_channel or record.channel == normalized_channel)
        ]
        return sorted(records, key=_recent_sort_key, reverse=True)

    def _candidate_records(self) -> list[SessionRecord]:
        records_by_key = {
            record.session_key: record
            for record in self._runtime.store.list_records()
            if record.availability != "deleted"
        }
        for entry in self._list_session_entries():
            key = normalize_text(entry.get("key"))
            if not key:
                continue
            existing = records_by_key.get(key)
            derived = _record_from_entry(entry, existing=existing)
            if derived is None:
                continue
            records_by_key[key] = derived
        return list(records_by_key.values())

    def _list_session_entries(self) -> list[dict[str, Any]]:
        list_sessions = getattr(self._session_manager, "list_sessions", None)
        if not callable(list_sessions):
            return []
        raw = list_sessions()
        return [dict(item) for item in raw] if isinstance(raw, list) else []

    @staticmethod
    def _snapshot(record: SessionRecord) -> dict[str, Any]:
        snapshot = record.as_snapshot()
        snapshot["id"] = record.session_ref or record.session_key
        delivery = _delivery_target_snapshot(record)
        snapshot["sendable"] = bool(delivery)
        if delivery:
            snapshot["delivery_channel"] = delivery["channel"]
            snapshot["delivery_chat_id"] = delivery["chat_id"]
            snapshot["delivery_metadata"] = dict(delivery["metadata"])
        return snapshot

    def _preferred_session_from_preferences(
        self,
        candidates: list[SessionRecord],
        *,
        channel: str | None,
        scope: str | None,
    ) -> tuple[dict[str, Any], SessionPreferenceRecord] | None:
        candidate_by_ref = {record.session_ref: record for record in candidates if record.session_ref}
        for preference in self._matching_preferences(channel=channel, scope=scope):
            matched = candidate_by_ref.get(preference.default_session_ref)
            if matched is None:
                continue
            snapshot = self._snapshot(matched)
            return snapshot, preference
        return None

    def _matching_preferences(
        self,
        *,
        channel: str | None,
        scope: str | None,
    ) -> list[SessionPreferenceRecord]:
        normalized_channel = normalize_channel(channel)
        normalized_scope = normalize_text(scope)
        scored: list[tuple[tuple[int, str, str], SessionPreferenceRecord]] = []
        for preference in self._runtime.store.list_preferences():
            channel_score = _preference_channel_score(preference, normalized_channel)
            if channel_score < 0:
                continue
            scope_score = _preference_scope_score(preference, normalized_scope)
            if scope_score < 0:
                continue
            scored.append(((scope_score + channel_score, preference.updated_at, preference.scope), preference))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [preference for _score, preference in scored]

    def _identity_map(self) -> dict[str, IdentityLinkRecord]:
        mapping: dict[str, IdentityLinkRecord] = {}
        for identity in self._runtime.store.list_identity_links():
            for member in identity.members:
                if member.session_ref:
                    mapping[member.session_ref] = identity
        return mapping


def _record_from_entry(entry: dict[str, Any], *, existing: SessionRecord | None) -> SessionRecord | None:
    key = normalize_text(entry.get("key"))
    if not key:
        return None
    if existing is None and not _entry_is_discoverable(entry):
        return None
    routing = entry.get("routing") if isinstance(entry.get("routing"), dict) else {}
    view = entry.get("view") if isinstance(entry.get("view"), dict) else {}
    current = existing.as_snapshot() if existing is not None else {}
    parsed_channel, parsed_peer, parsed_thread = _parse_session_route(key)
    availability = _derive_availability(entry, existing=existing)
    return SessionRecord.create(
        session_ref=current.get("session_ref", ""),
        session_key=key,
        channel=current.get("channel", "") or parsed_channel,
        account_id=current.get("account_id", ""),
        peer_id=current.get("peer_id", "") or parsed_peer,
        thread_id=current.get("thread_id", "") or parsed_thread,
        title=view.get("title") or current.get("title", ""),
        handle=current.get("handle", "") or parsed_peer,
        kind=routing.get("session_kind") or current.get("kind", ""),
        updated_at=entry.get("updated_at") or current.get("updated_at", ""),
        last_active_at=current.get("last_active_at", "") or entry.get("updated_at") or current.get("updated_at", ""),
        availability=availability,
        archived=availability == "archived",
        participants_preview=current.get("participants_preview", ()),
    )


def _entry_is_discoverable(entry: dict[str, Any]) -> bool:
    has_messages = entry.get("has_messages")
    if has_messages is True:
        return True
    message_count = entry.get("message_count")
    return isinstance(message_count, int) and message_count > 0


def _derive_availability(entry: dict[str, Any], *, existing: SessionRecord | None) -> str:
    if existing is not None and existing.availability in {"deleted", "archived", "unreachable"}:
        return existing.availability
    runtime = entry.get("runtime") if isinstance(entry.get("runtime"), dict) else {}
    if bool(runtime.get("is_running")):
        return "active"
    if existing is not None:
        return existing.availability
    return "dormant"


def _lookup_match(
    record: SessionRecord,
    query: str,
    identity: IdentityLinkRecord | None,
) -> tuple[int, int, int, str, str] | None:
    normalized_query = query.lower()
    fields = _search_fields(record, identity)
    joined = " ".join(fields)
    if normalized_query not in joined and not all(token in joined for token in _query_tokens(query)):
        return None
    exact = int(any(field == normalized_query for field in fields))
    prefix = int(any(field.startswith(normalized_query) for field in fields))
    contains = int(normalized_query in joined)
    identity_hit = int(identity is not None and _identity_matches(identity, normalized_query))
    return exact, prefix, identity_hit, contains, record.updated_at


def _search_fields(record: SessionRecord, identity: IdentityLinkRecord | None) -> list[str]:
    values = [
        record.title,
        record.handle,
        record.peer_id,
        record.session_key,
        record.session_ref,
        record.binding_key(),
        record.channel,
    ]
    if identity is not None:
        values.append(identity.identity_ref)
        for member in identity.members:
            values.extend([member.peer_id, member.channel, member.session_ref])
    return [value.lower() for value in values if value]


def _identity_matches(identity: IdentityLinkRecord, normalized_query: str) -> bool:
    if identity.identity_ref.lower() == normalized_query:
        return True
    return any(
        normalized_query in " ".join(part for part in [member.channel, member.peer_id, member.session_ref] if part).lower()
        for member in identity.members
    )


def _query_tokens(query: str) -> tuple[str, ...]:
    tokens = [part for part in _QUERY_SPLIT_RE.split(query.lower()) if part]
    return tuple(tokens)


def _normalize_limit(value: int | None, *, default: int) -> int:
    if isinstance(value, int) and value > 0:
        return value
    return default


def _recent_sort_key(record: SessionRecord) -> tuple[str, str, str]:
    return record.last_active_at or record.updated_at, record.updated_at, record.session_key


def _preference_channel_score(preference: SessionPreferenceRecord, channel: str) -> int:
    if preference.channel and channel and preference.channel == channel:
        return 2
    if not preference.channel:
        return 1
    if not channel:
        return 0
    return -1


def _preference_scope_score(preference: SessionPreferenceRecord, scope: str) -> int:
    if preference.scope and scope and preference.scope == scope:
        return 4
    if preference.scope == "global":
        return 1
    if not preference.scope:
        return 0
    if not scope:
        return 0
    return -1


def _parse_session_route(session_key: str) -> tuple[str, str, str]:
    normalized = normalize_text(session_key)
    if ":" not in normalized:
        return "", "", ""
    channel, remainder = normalized.split(":", 1)
    route_head = remainder.split("::", 1)[0]
    normalized_channel = normalize_channel(channel)
    if normalized_channel == "telegram" and ":topic:" in route_head:
        peer_id, thread_id = route_head.split(":topic:", 1)
        return normalized_channel, normalize_text(peer_id), normalize_text(thread_id)
    if normalized_channel == "slack" and ":" in route_head:
        peer_id, thread_id = route_head.split(":", 1)
        return normalized_channel, normalize_text(peer_id), normalize_text(thread_id)
    return normalized_channel, normalize_text(route_head), ""


def _delivery_target_snapshot(record: SessionRecord) -> dict[str, Any]:
    if (
        not record.session_ref
        or not record.channel
        or not record.peer_id
        or record.channel in _UNSENDABLE_CHANNELS
        or record.availability == "deleted"
    ):
        return {}
    return {
        "session_ref": record.session_ref,
        "session_key": record.session_key,
        "channel": record.channel,
        "chat_id": record.peer_id,
        "metadata": _delivery_metadata(record),
    }


def _delivery_metadata(record: SessionRecord) -> dict[str, Any]:
    thread_id = normalize_text(record.thread_id)
    if not thread_id:
        return {}
    if record.channel == "telegram":
        return {"message_thread_id": thread_id}
    if record.channel == "slack":
        return {"slack": {"thread_ts": thread_id, "channel_type": "channel"}}
    return {}
