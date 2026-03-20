from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from threading import RLock

from loguru import logger

from bao.utils.db import get_db, open_or_create_table

from ._session_directory_models import (
    IdentityLinkRecord,
    SessionBindingRecord,
    SessionPreferenceRecord,
    SessionRecord,
)

_RECORDS_TABLE = "hub_session_directory_records"
_BINDINGS_TABLE = "hub_session_directory_bindings"
_PREFERENCES_TABLE = "hub_session_directory_preferences"
_IDENTITIES_TABLE = "hub_session_directory_identities"

_RECORD_SAMPLE = [{
    "session_key": "_init_",
    "session_ref": "_init_",
    "channel": "",
    "account_id": "",
    "peer_id": "",
    "thread_id": "",
    "title": "",
    "handle": "",
    "kind": "",
    "updated_at": "",
    "last_active_at": "",
    "availability": "dormant",
    "archived": False,
    "participants_preview_json": "[]",
    "binding_key": "",
}]

_BINDING_SAMPLE = [{
    "binding_key": "_init_",
    "session_ref": "_init_",
    "source": "observed",
    "updated_at": "",
}]

_PREFERENCE_SAMPLE = [{
    "scope": "_init_",
    "channel": "",
    "default_session_ref": "",
    "reason": "explicit",
    "updated_at": "",
}]

_IDENTITY_SAMPLE = [{
    "identity_ref": "_init_",
    "members_json": "[]",
    "confidence": "explicit",
    "updated_at": "",
}]


def _escape(value: object) -> str:
    return str(value or "").replace("'", "''")


@dataclass(frozen=True, slots=True)
class SessionDirectorySnapshot:
    records: tuple[SessionRecord, ...]
    bindings: tuple[SessionBindingRecord, ...]
    preferences: tuple[SessionPreferenceRecord, ...]
    identities: tuple[IdentityLinkRecord, ...]


class SessionDirectoryStore:
    def __init__(self, workspace: str | Path) -> None:
        self._workspace = Path(str(workspace)).expanduser()
        self._lock = RLock()
        self._db = None
        self._records = None
        self._bindings = None
        self._preferences = None
        self._identities = None

    def get_record(self, session_key: object) -> SessionRecord | None:
        normalized_key = str(session_key or "").strip()
        if not normalized_key:
            return None
        with self._lock:
            rows = self._records_table().search().where(
                f"session_key = '{_escape(normalized_key)}'"
            ).limit(1).to_list()
        return self._decode_record(rows[0]) if rows else None

    def list_records(self) -> list[SessionRecord]:
        with self._lock:
            try:
                rows = self._records_table().search().where("session_key != '_init_'").to_list()
            except Exception:
                return []
        records = [self._decode_record(row) for row in rows]
        return sorted(
            [record for record in records if record is not None],
            key=lambda record: (record.updated_at, record.session_key),
            reverse=True,
        )

    def get_record_by_ref(self, session_ref: object) -> SessionRecord | None:
        normalized_ref = str(session_ref or "").strip()
        if not normalized_ref:
            return None
        with self._lock:
            rows = self._records_table().search().where(
                f"session_ref = '{_escape(normalized_ref)}'"
            ).limit(1).to_list()
        return self._decode_record(rows[0]) if rows else None

    def get_binding(self, binding_key: object) -> SessionBindingRecord | None:
        normalized_key = str(binding_key or "").strip()
        if not normalized_key:
            return None
        with self._lock:
            rows = self._bindings_table().search().where(
                f"binding_key = '{_escape(normalized_key)}'"
            ).limit(1).to_list()
        return self._decode_binding(rows[0]) if rows else None

    def list_bindings(self) -> list[SessionBindingRecord]:
        with self._lock:
            try:
                rows = self._bindings_table().search().where("binding_key != '_init_'").to_list()
            except Exception:
                return []
        bindings = [self._decode_binding(row) for row in rows]
        return [binding for binding in bindings if binding is not None]

    def get_preference(self, scope: object, channel: object = "") -> SessionPreferenceRecord | None:
        normalized_scope = str(scope or "").strip()
        normalized_channel = str(channel or "").strip().lower()
        if not normalized_scope:
            return None
        where = f"scope = '{_escape(normalized_scope)}'"
        if normalized_channel:
            where += f" AND channel = '{_escape(normalized_channel)}'"
        with self._lock:
            rows = self._preferences_table().search().where(where).to_list()
        preferences = [self._decode_preference(row) for row in rows]
        valid = [item for item in preferences if item is not None]
        if not valid:
            return None
        return max(valid, key=lambda item: (item.updated_at, item.scope, item.channel))

    def list_preferences(self) -> list[SessionPreferenceRecord]:
        with self._lock:
            try:
                rows = self._preferences_table().search().where("scope != '_init_'").to_list()
            except Exception:
                return []
        preferences = [self._decode_preference(row) for row in rows]
        return sorted(
            [preference for preference in preferences if preference is not None],
            key=lambda preference: (preference.updated_at, preference.scope, preference.channel),
            reverse=True,
        )

    def upsert_preference(self, preference: SessionPreferenceRecord) -> None:
        row = preference.as_snapshot()
        with self._lock:
            table = self._preferences_table()
            table.delete(
                f"scope = '{_escape(preference.scope)}' AND channel = '{_escape(preference.channel)}'"
            )
            table.add([row])

    def get_identity_link(self, identity_ref: object) -> IdentityLinkRecord | None:
        normalized_ref = str(identity_ref or "").strip()
        if not normalized_ref:
            return None
        with self._lock:
            rows = self._identities_table().search().where(
                f"identity_ref = '{_escape(normalized_ref)}'"
            ).limit(1).to_list()
        return self._decode_identity(rows[0]) if rows else None

    def list_identity_links(self) -> list[IdentityLinkRecord]:
        with self._lock:
            try:
                rows = self._identities_table().search().where("identity_ref != '_init_'").to_list()
            except Exception:
                return []
        identities = [self._decode_identity(row) for row in rows]
        return sorted(
            [identity for identity in identities if identity is not None],
            key=lambda identity: (identity.updated_at, identity.identity_ref),
            reverse=True,
        )

    def upsert_identity_link(self, identity: IdentityLinkRecord) -> None:
        row = {
            "identity_ref": identity.identity_ref,
            "members_json": json.dumps([member.as_snapshot() for member in identity.members], ensure_ascii=False),
            "confidence": identity.confidence,
            "updated_at": identity.updated_at,
        }
        with self._lock:
            table = self._identities_table()
            table.delete(f"identity_ref = '{_escape(identity.identity_ref)}'")
            table.add([row])

    def snapshot(self) -> SessionDirectorySnapshot:
        return SessionDirectorySnapshot(
            records=tuple(self.list_records()),
            bindings=tuple(self.list_bindings()),
            preferences=tuple(self.list_preferences()),
            identities=tuple(self.list_identity_links()),
        )

    def upsert_record(self, record: SessionRecord) -> None:
        payload = record.as_snapshot()
        row = {
            "session_key": record.session_key,
            "session_ref": record.session_ref,
            "channel": record.channel,
            "account_id": record.account_id,
            "peer_id": record.peer_id,
            "thread_id": record.thread_id,
            "title": record.title,
            "handle": record.handle,
            "kind": record.kind,
            "updated_at": record.updated_at,
            "last_active_at": record.last_active_at,
            "availability": record.availability,
            "archived": bool(record.archived),
            "participants_preview_json": json.dumps(payload["participants_preview"], ensure_ascii=False),
            "binding_key": payload["binding_key"],
        }
        with self._lock:
            table = self._records_table()
            table.delete(f"session_key = '{_escape(record.session_key)}'")
            table.add([row])

    def upsert_binding(self, binding: SessionBindingRecord) -> None:
        with self._lock:
            table = self._bindings_table()
            table.delete(f"binding_key = '{_escape(binding.binding_key)}'")
            table.add([binding.as_snapshot()])

    def delete_observed_bindings_for_session(self, session_ref: object) -> None:
        normalized_ref = str(session_ref or "").strip()
        if not normalized_ref:
            return
        with self._lock:
            self._bindings_table().delete(
                f"session_ref = '{_escape(normalized_ref)}' AND source = 'observed'"
            )

    def _records_table(self):
        if self._records is not None:
            return self._records
        with self._lock:
            if self._records is None:
                table, created = open_or_create_table(self._db_connection(), _RECORDS_TABLE, _RECORD_SAMPLE)
                self._records = table
                if created:
                    self._ensure_index(table, "session_key")
                    self._ensure_index(table, "session_ref")
                    self._ensure_index(table, "binding_key")
            return self._records

    def _bindings_table(self):
        if self._bindings is not None:
            return self._bindings
        with self._lock:
            if self._bindings is None:
                table, created = open_or_create_table(self._db_connection(), _BINDINGS_TABLE, _BINDING_SAMPLE)
                self._bindings = table
                if created:
                    self._ensure_index(table, "binding_key")
                    self._ensure_index(table, "session_ref")
            return self._bindings

    def _preferences_table(self):
        if self._preferences is not None:
            return self._preferences
        with self._lock:
            if self._preferences is None:
                table, created = open_or_create_table(self._db_connection(), _PREFERENCES_TABLE, _PREFERENCE_SAMPLE)
                self._preferences = table
                if created:
                    self._ensure_index(table, "scope")
                    self._ensure_index(table, "channel")
            return self._preferences

    def _identities_table(self):
        if self._identities is not None:
            return self._identities
        with self._lock:
            if self._identities is None:
                table, created = open_or_create_table(self._db_connection(), _IDENTITIES_TABLE, _IDENTITY_SAMPLE)
                self._identities = table
                if created:
                    self._ensure_index(table, "identity_ref")
            return self._identities

    def _db_connection(self):
        if self._db is None:
            self._db = get_db(self._workspace)
        return self._db

    @staticmethod
    def _ensure_index(table, column: str) -> None:
        try:
            table.create_scalar_index(column, replace=False)
        except Exception as exc:
            logger.debug("Skip session directory index {}: {}", column, exc)

    @staticmethod
    def _decode_record(row: dict[str, object]) -> SessionRecord | None:
        try:
            participants = json.loads(str(row.get("participants_preview_json") or "[]"))
        except Exception:
            participants = []
        if not isinstance(participants, Iterable):
            participants = []
        try:
            return SessionRecord.create(
                session_ref=row.get("session_ref"),
                session_key=row.get("session_key"),
                channel=row.get("channel"),
                account_id=row.get("account_id"),
                peer_id=row.get("peer_id"),
                thread_id=row.get("thread_id"),
                title=row.get("title"),
                handle=row.get("handle"),
                kind=row.get("kind"),
                updated_at=row.get("updated_at"),
                last_active_at=row.get("last_active_at"),
                availability=row.get("availability"),
                archived=row.get("archived"),
                participants_preview=participants,
            )
        except Exception:
            return None

    @staticmethod
    def _decode_binding(row: dict[str, object]) -> SessionBindingRecord | None:
        try:
            return SessionBindingRecord(
                binding_key=str(row.get("binding_key") or "").strip(),
                session_ref=str(row.get("session_ref") or "").strip(),
                source=str(row.get("source") or "observed").strip() or "observed",
                updated_at=str(row.get("updated_at") or "").strip(),
            )
        except Exception:
            return None

    @staticmethod
    def _decode_preference(row: dict[str, object]) -> SessionPreferenceRecord | None:
        try:
            return SessionPreferenceRecord.create(
                scope=row.get("scope"),
                channel=row.get("channel"),
                default_session_ref=row.get("default_session_ref"),
                reason=row.get("reason"),
                updated_at=row.get("updated_at"),
            )
        except Exception:
            return None

    @staticmethod
    def _decode_identity(row: dict[str, object]) -> IdentityLinkRecord | None:
        try:
            members = json.loads(str(row.get("members_json") or "[]"))
        except Exception:
            members = []
        if not isinstance(members, list):
            members = []
        try:
            return IdentityLinkRecord.create(
                identity_ref=row.get("identity_ref"),
                members=members,
                confidence=row.get("confidence"),
                updated_at=row.get("updated_at"),
            )
        except Exception:
            return None
