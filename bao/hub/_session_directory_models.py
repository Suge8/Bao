from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from ._normalization import normalize_channel, normalize_text
from ._session_directory_identity import (
    IdentityConfidence,
    SessionAvailability,
    SessionBindingSource,
    SessionPreferenceReason,
    build_binding_key,
    build_session_ref,
    normalize_binding_source,
    normalize_identity_confidence,
    normalize_identity_member_mapping,
    normalize_preference_reason,
    normalize_preview_items,
    normalize_session_availability,
)


@dataclass(frozen=True, slots=True)
class SessionRecord:
    session_ref: str
    session_key: str
    channel: str
    account_id: str = ""
    peer_id: str = ""
    thread_id: str = ""
    title: str = ""
    handle: str = ""
    kind: str = ""
    updated_at: str = ""
    last_active_at: str = ""
    availability: SessionAvailability = "dormant"
    archived: bool = False
    participants_preview: tuple[str, ...] = ()

    @classmethod
    def create(
        cls,
        *,
        session_key: object,
        channel: object,
        account_id: object = "",
        peer_id: object = "",
        thread_id: object = "",
        title: object = "",
        handle: object = "",
        kind: object = "",
        updated_at: object = "",
        last_active_at: object = "",
        availability: object = "dormant",
        archived: object = False,
        participants_preview: Iterable[object] | None = None,
        session_ref: object = "",
    ) -> "SessionRecord":
        normalized_session_key = normalize_text(session_key)
        normalized_channel = normalize_channel(channel)
        normalized_account = normalize_text(account_id)
        normalized_peer = normalize_text(peer_id)
        normalized_thread = normalize_text(thread_id)
        return cls(
            session_ref=normalize_text(session_ref)
            or build_session_ref(
                session_key=normalized_session_key,
                channel=normalized_channel,
                account_id=normalized_account,
                peer_id=normalized_peer,
                thread_id=normalized_thread,
            ),
            session_key=normalized_session_key,
            channel=normalized_channel,
            account_id=normalized_account,
            peer_id=normalized_peer,
            thread_id=normalized_thread,
            title=normalize_text(title),
            handle=normalize_text(handle),
            kind=normalize_text(kind),
            updated_at=normalize_text(updated_at),
            last_active_at=normalize_text(last_active_at),
            availability=normalize_session_availability(availability),
            archived=bool(archived),
            participants_preview=normalize_preview_items(participants_preview),
        )

    def binding_key(self) -> str:
        return build_binding_key(
            channel=self.channel,
            account_id=self.account_id,
            peer_id=self.peer_id,
            thread_id=self.thread_id,
        )

    def as_snapshot(self) -> dict[str, Any]:
        return {
            "session_ref": self.session_ref,
            "session_key": self.session_key,
            "channel": self.channel,
            "account_id": self.account_id,
            "peer_id": self.peer_id,
            "thread_id": self.thread_id,
            "title": self.title,
            "handle": self.handle,
            "kind": self.kind,
            "updated_at": self.updated_at,
            "last_active_at": self.last_active_at,
            "availability": self.availability,
            "archived": self.archived,
            "participants_preview": list(self.participants_preview),
            "binding_key": self.binding_key(),
        }


@dataclass(frozen=True, slots=True)
class SessionBindingRecord:
    binding_key: str
    session_ref: str
    source: SessionBindingSource = "observed"
    updated_at: str = ""

    @classmethod
    def create(
        cls,
        *,
        session_ref: object,
        channel: object,
        peer_id: object,
        account_id: object = "",
        thread_id: object = "",
        source: object = "observed",
        updated_at: object = "",
    ) -> "SessionBindingRecord":
        return cls(
            binding_key=build_binding_key(
                channel=channel,
                account_id=account_id,
                peer_id=peer_id,
                thread_id=thread_id,
            ),
            session_ref=normalize_text(session_ref),
            source=normalize_binding_source(source),
            updated_at=normalize_text(updated_at),
        )

    def as_snapshot(self) -> dict[str, str]:
        return {
            "binding_key": self.binding_key,
            "session_ref": self.session_ref,
            "source": self.source,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True, slots=True)
class SessionPreferenceRecord:
    scope: str
    channel: str
    default_session_ref: str
    reason: SessionPreferenceReason = "explicit"
    updated_at: str = ""

    @classmethod
    def create(
        cls,
        *,
        scope: object,
        channel: object,
        default_session_ref: object,
        reason: object = "explicit",
        updated_at: object = "",
    ) -> "SessionPreferenceRecord":
        return cls(
            scope=normalize_text(scope),
            channel=normalize_channel(channel),
            default_session_ref=normalize_text(default_session_ref),
            reason=normalize_preference_reason(reason),
            updated_at=normalize_text(updated_at),
        )

    def as_snapshot(self) -> dict[str, str]:
        return {
            "scope": self.scope,
            "channel": self.channel,
            "default_session_ref": self.default_session_ref,
            "reason": self.reason,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True, slots=True)
class IdentityMemberRecord:
    channel: str
    peer_id: str
    account_id: str = ""
    thread_id: str = ""
    session_ref: str = ""

    @classmethod
    def create(
        cls,
        *,
        channel: object,
        peer_id: object,
        account_id: object = "",
        thread_id: object = "",
        session_ref: object = "",
    ) -> "IdentityMemberRecord":
        return cls(
            channel=normalize_channel(channel),
            peer_id=normalize_text(peer_id),
            account_id=normalize_text(account_id),
            thread_id=normalize_text(thread_id),
            session_ref=normalize_text(session_ref),
        )

    def as_snapshot(self) -> dict[str, str]:
        return {
            "channel": self.channel,
            "peer_id": self.peer_id,
            "account_id": self.account_id,
            "thread_id": self.thread_id,
            "session_ref": self.session_ref,
        }


@dataclass(frozen=True, slots=True)
class IdentityLinkRecord:
    identity_ref: str
    members: tuple[IdentityMemberRecord, ...]
    confidence: IdentityConfidence = "explicit"
    updated_at: str = ""

    @classmethod
    def create(
        cls,
        *,
        identity_ref: object,
        members: Iterable[IdentityMemberRecord | Mapping[str, object]],
        confidence: object = "explicit",
        updated_at: object = "",
    ) -> "IdentityLinkRecord":
        normalized_members: list[IdentityMemberRecord] = []
        for value in members:
            if isinstance(value, IdentityMemberRecord):
                member = value
            elif isinstance(value, Mapping):
                member = IdentityMemberRecord.create(**normalize_identity_member_mapping(value))
            else:
                continue
            if not member.channel or not member.peer_id:
                continue
            normalized_members.append(member)
        return cls(
            identity_ref=normalize_text(identity_ref),
            members=tuple(normalized_members),
            confidence=normalize_identity_confidence(confidence),
            updated_at=normalize_text(updated_at),
        )

    def as_snapshot(self) -> dict[str, Any]:
        return {
            "identity_ref": self.identity_ref,
            "members": [member.as_snapshot() for member in self.members],
            "confidence": self.confidence,
            "updated_at": self.updated_at,
        }
