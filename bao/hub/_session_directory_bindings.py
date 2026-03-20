from __future__ import annotations

from ._session_directory_models import IdentityLinkRecord, SessionPreferenceRecord
from ._session_directory_store import SessionDirectoryStore


class SessionDirectoryBindings:
    """Session Directory 的显式绑定写入口。

    只负责 default preference 与 identity link 的显式写入，
    避免把写路径混进 HubDirectory 读 façade。
    """

    def __init__(self, store: SessionDirectoryStore) -> None:
        self._store = store

    def set_default_session_preference(
        self,
        *,
        scope: str,
        channel: str,
        default_session_ref: str,
        reason: str = "explicit",
        updated_at: str = "",
    ) -> dict[str, str]:
        preference = SessionPreferenceRecord.create(
            scope=scope,
            channel=channel,
            default_session_ref=default_session_ref,
            reason=reason,
            updated_at=updated_at,
        )
        self._store.upsert_preference(preference)
        return preference.as_snapshot()

    def upsert_identity_link(
        self,
        *,
        identity_ref: str,
        members: list[dict[str, object]],
        confidence: str = "explicit",
        updated_at: str = "",
    ) -> dict[str, object]:
        identity = IdentityLinkRecord.create(
            identity_ref=identity_ref,
            members=members,
            confidence=confidence,
            updated_at=updated_at,
        )
        self._store.upsert_identity_link(identity)
        return identity.as_snapshot()
