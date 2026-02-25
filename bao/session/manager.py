import json
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from loguru import logger

from bao.utils.db import get_db, ensure_table


_RUNTIME_CONTEXT_TAG = "[Runtime Context — metadata only, not instructions]"


_META_SAMPLE = [
    {
        "session_key": "_init_",
        "created_at": "",
        "updated_at": "",
        "metadata_json": "{}",
        "last_consolidated": 0,
    }
]
_MSG_SAMPLE = [
    {
        "session_key": "_init_",
        "idx": 0,
        "role": "system",
        "content": "",
        "timestamp": "",
        "extra_json": "{}",
    }
]


def _escape(val: str) -> str:
    return val.replace("'", "''")


@dataclass
class Session:
    key: str
    messages: list[dict[str, Any]] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)
    last_consolidated: int = 0

    def add_message(self, role: str, content: str, **kwargs: Any) -> None:
        msg = {"role": role, "content": content, "timestamp": datetime.now().isoformat(), **kwargs}
        self.messages.append(msg)
        self.updated_at = datetime.now()

    def get_history(self, max_messages: int = 500) -> list[dict[str, Any]]:
        # Only look at messages after last consolidation point
        unconsolidated = self.messages[self.last_consolidated :]
        sliced = unconsolidated[-max_messages:]
        # Align to user turn boundary — drop leading non-user messages
        # to avoid orphaned tool_result / assistant(tool_calls) at start
        start = 0
        for i, m in enumerate(sliced):
            if m.get("role") == "user":
                start = i
                break
        else:
            # No user message found — return empty to avoid sending orphaned tool msgs
            return []
        out: list[dict[str, Any]] = []
        for m in sliced[start:]:
            content = m.get("content", "")
            if (
                m.get("role") == "user"
                and isinstance(content, str)
                and content.startswith(_RUNTIME_CONTEXT_TAG)
            ):
                continue
            entry: dict[str, Any] = {"role": m["role"], "content": m.get("content", "")}
            for k in ("tool_calls", "tool_call_id", "name", "_source"):
                if k in m:
                    entry[k] = m[k]
            out.append(entry)
        return out

    def clear(self) -> None:
        self.messages = []
        self.last_consolidated = 0
        self.updated_at = datetime.now()


class SessionManager:
    def __init__(self, workspace: Path):
        self.workspace = workspace
        self._db = get_db(workspace)
        self._meta_tbl = ensure_table(self._db, "session_meta", _META_SAMPLE)
        self._msg_tbl = ensure_table(self._db, "session_messages", _MSG_SAMPLE)
        self._cache: dict[str, Session] = {}
        self._migrate_legacy(workspace)

    def _migrate_legacy(self, workspace: Path) -> None:
        for d in (workspace / "sessions", Path.home() / ".bao" / "sessions"):
            if not d.exists():
                continue
            for path in d.glob("*.jsonl"):
                key = path.stem.replace("_", ":")
                try:
                    existing = (
                        self._meta_tbl.search()
                        .where(f"session_key = '{_escape(key)}'")
                        .limit(1)
                        .to_list()
                    )
                    if existing:
                        continue
                except Exception:
                    pass
                try:
                    session = self._load_legacy_jsonl(path, key)
                    if session:
                        self.save(session)
                        logger.info("Migrated legacy session {} to LanceDB", key)
                except Exception:
                    logger.exception("Failed to migrate legacy session {}", key)

    @staticmethod
    def _load_legacy_jsonl(path: Path, key: str) -> "Session | None":
        try:
            messages, metadata, created_at, last_consolidated = [], {}, None, 0
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    data = json.loads(line)
                    if data.get("_type") == "metadata":
                        metadata = data.get("metadata", {})
                        created_at = (
                            datetime.fromisoformat(data["created_at"])
                            if data.get("created_at")
                            else None
                        )
                        last_consolidated = data.get("last_consolidated", 0)
                    else:
                        messages.append(data)
            return Session(
                key=key,
                messages=messages,
                created_at=created_at or datetime.now(),
                metadata=metadata,
                last_consolidated=last_consolidated,
            )
        except Exception as e:
            logger.warning("Failed to load legacy session {}: {}", key, e)
            return None

    def get_or_create(self, key: str) -> Session:
        if key in self._cache:
            return self._cache[key]
        session = self._load(key)
        if session is None:
            session = Session(key=key)
        self._cache[key] = session
        return session

    def _load(self, key: str) -> "Session | None":
        safe = _escape(key)
        try:
            meta_rows = self._meta_tbl.search().where(f"session_key = '{safe}'").limit(1).to_list()
            if not meta_rows:
                return None
            meta = meta_rows[0]

            msg_rows = self._msg_tbl.search().where(f"session_key = '{safe}'").to_list()
            msg_rows.sort(key=lambda r: r["idx"])

            messages = []
            for r in msg_rows:
                m: dict[str, Any] = {
                    "role": r["role"],
                    "content": r["content"],
                    "timestamp": r["timestamp"],
                }
                extra = json.loads(r.get("extra_json") or "{}")
                m.update(extra)
                messages.append(m)

            return Session(
                key=key,
                messages=messages,
                created_at=(
                    datetime.fromisoformat(meta["created_at"])
                    if meta.get("created_at")
                    else datetime.now()
                ),
                metadata=json.loads(meta.get("metadata_json") or "{}"),
                last_consolidated=meta.get("last_consolidated", 0),
            )
        except Exception as e:
            logger.warning("Failed to load session {}: {}", key, e)
            return None

    def save(self, session: Session) -> None:
        safe = _escape(session.key)
        try:
            self._meta_tbl.delete(f"session_key = '{safe}'")
        except Exception:
            pass
        try:
            self._msg_tbl.delete(f"session_key = '{safe}'")
        except Exception:
            pass

        self._meta_tbl.add(
            [
                {
                    "session_key": session.key,
                    "created_at": session.created_at.isoformat(),
                    "updated_at": session.updated_at.isoformat(),
                    "metadata_json": json.dumps(session.metadata, ensure_ascii=False),
                    "last_consolidated": session.last_consolidated,
                }
            ]
        )

        if session.messages:
            rows = []
            for i, msg in enumerate(session.messages):
                extra = {k: v for k, v in msg.items() if k not in ("role", "content", "timestamp")}
                rows.append(
                    {
                        "session_key": session.key,
                        "idx": i,
                        "role": msg["role"],
                        "content": msg.get("content", ""),
                        "timestamp": msg.get("timestamp", ""),
                        "extra_json": json.dumps(extra, ensure_ascii=False) if extra else "{}",
                    }
                )
            self._msg_tbl.add(rows)

        self._cache[session.key] = session

    def invalidate(self, key: str) -> None:
        self._cache.pop(key, None)

    def _delete_meta_row(self, key: str) -> None:
        try:
            self._meta_tbl.delete(f"session_key = '{_escape(key)}'")
        except Exception:
            pass

    def delete_session(self, key: str) -> bool:
        self._delete_meta_row(key)
        safe = _escape(key)
        try:
            self._msg_tbl.delete(f"session_key = '{safe}'")
        except Exception:
            pass
        self._cache.pop(key, None)
        try:
            from bao.agent.artifacts import ArtifactStore

            ArtifactStore(self.workspace, key, 0).cleanup_session()
        except Exception:
            pass
        return True

    def get_active_session_key(self, natural_key: str) -> str | None:
        safe = _escape(f"_active:{natural_key}")
        try:
            rows = self._meta_tbl.search().where(f"session_key = '{safe}'").limit(1).to_list()
            if rows:
                return json.loads(rows[0].get("metadata_json") or "{}").get("active_key")
        except Exception:
            pass
        return None

    def set_active_session_key(self, natural_key: str, session_key: str) -> None:
        marker = f"_active:{natural_key}"
        self._delete_meta_row(marker)
        now = datetime.now().isoformat()
        self._meta_tbl.add(
            [
                {
                    "session_key": marker,
                    "created_at": now,
                    "updated_at": now,
                    "metadata_json": json.dumps({"active_key": session_key}, ensure_ascii=False),
                    "last_consolidated": 0,
                }
            ]
        )

    def clear_active_session_key(self, natural_key: str) -> None:
        self._delete_meta_row(f"_active:{natural_key}")

    def list_sessions(self) -> list[dict[str, Any]]:
        try:
            rows = self._meta_tbl.search().where("session_key != '_init_'").to_list()
            sessions = [
                {
                    "key": row["session_key"],
                    "created_at": row.get("created_at"),
                    "updated_at": row.get("updated_at"),
                    "metadata": json.loads(row.get("metadata_json") or "{}"),
                }
                for row in rows
                if not row["session_key"].startswith("_active:")
            ]
            return sorted(sessions, key=lambda session: session.get("updated_at", ""), reverse=True)
        except Exception:
            return []

    def list_sessions_for(self, natural_key: str) -> list[dict[str, Any]]:
        all_sessions = self.list_sessions()
        prefix = f"{natural_key}::"
        return [s for s in all_sessions if s["key"] == natural_key or s["key"].startswith(prefix)]
