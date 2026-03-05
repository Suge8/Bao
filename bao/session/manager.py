import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger

from bao.utils.db import ensure_table, get_db

# legacy safety net — runtime context is no longer injected as user message,
# but keep filtering in case old sessions contain such entries.
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

    def add_message(self, role: str, content: str | list[dict[str, Any]], **kwargs: Any) -> None:
        if role == "user" and isinstance(content, list):
            content = [
                {"type": "text", "text": "[image]"}
                if c.get("type") == "image_url"
                and c.get("image_url", {}).get("url", "").startswith("data:image/")
                else c
                for c in content
            ]
        msg = {"role": role, "content": content, "timestamp": datetime.now().isoformat(), **kwargs}
        self.messages.append(msg)
        if role == "assistant":
            self.metadata["desktop_last_ai_at"] = msg["timestamp"]
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
            # legacy safety net: filter old runtime context user messages
            if (
                m.get("role") == "user"
                and isinstance(content, str)
                and content.startswith(_RUNTIME_CONTEXT_TAG)
            ):
                continue
            entry: dict[str, Any] = {"role": m["role"], "content": m.get("content", "")}
            for k in ("tool_calls", "tool_call_id", "name", "_source", "status"):
                if k in m:
                    entry[k] = m[k]
            out.append(entry)
        return out

    def get_display_history(self, max_messages: int = 500) -> list[dict[str, Any]]:
        unconsolidated = self.messages[self.last_consolidated :]
        sliced = unconsolidated[-max_messages:]
        out: list[dict[str, Any]] = []
        for m in sliced:
            content = m.get("content", "")
            # legacy safety net: filter old runtime context user messages
            if (
                m.get("role") == "user"
                and isinstance(content, str)
                and content.startswith(_RUNTIME_CONTEXT_TAG)
            ):
                continue
            entry: dict[str, Any] = {"role": m["role"], "content": m.get("content", "")}
            for k in ("tool_calls", "tool_call_id", "name", "_source", "status"):
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
        self._active_cache: dict[str, str] = {}
        self._migrate_legacy(workspace)
        self._ensure_indexes()

    def _ensure_indexes(self) -> None:
        """Create scalar indexes for frequently filtered columns."""
        try:
            self._meta_tbl.create_scalar_index("session_key", replace=False)
            self._msg_tbl.create_scalar_index("session_key", replace=False)
            self._msg_tbl.create_scalar_index("idx", replace=False)
            logger.debug("📊 索引已创建 / indexes created: session_key, idx")
        except Exception as e:
            logger.debug("⚠️ 索引创建跳过 / index creation skipped: {}", e)

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
                        logger.debug("🗂️ 旧会话已迁 / migrated: {} to LanceDB", key)
                except Exception:
                    logger.exception("❌ 旧会话迁移失败 / migration failed: {}", key)

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
            logger.warning("⚠️ 旧会话加载失败 / load failed: {} — {}", key, e)
            return None

    def get_or_create(self, key: str) -> Session:
        if key in self._cache:
            return self._cache[key]
        session = self._load(key)
        if session is None:
            session = Session(key=key)
        self._cache[key] = session
        return session

    def session_exists(self, key: str) -> bool:
        """Check if a session exists (cache-first, then DB)."""
        if key in self._cache:
            return True
        return self._load(key) is not None

    def _load(self, key: str) -> "Session | None":
        import os
        import time

        _profile = os.getenv("BAO_DESKTOP_PROFILE") == "1"
        t0 = time.perf_counter() if _profile else 0
        safe = _escape(key)
        try:
            meta_rows = self._meta_tbl.search().where(f"session_key = '{safe}'").limit(1).to_list()
            if not meta_rows:
                return None
            meta = meta_rows[0]
            t1 = time.perf_counter() if _profile else 0

            msg_rows = self._msg_tbl.search().where(f"session_key = '{safe}'").to_list()
            msg_rows.sort(key=lambda r: r["idx"])
            t2 = time.perf_counter() if _profile else 0

            messages = []
            for r in msg_rows:
                m: dict[str, Any] = {
                    "role": r["role"],
                    "content": r["content"],
                    "timestamp": r["timestamp"],
                }
                extra_json = r.get("extra_json") or "{}"
                if extra_json != "{}":
                    m.update(json.loads(extra_json))
                messages.append(m)
            t3 = time.perf_counter() if _profile else 0

            if _profile:
                logger.debug(
                    "📊 Session._load: meta={:.3f}s, msgs={:.3f}s, parse={:.3f}s, total_msgs={}",
                    t1 - t0,
                    t2 - t1,
                    t3 - t2,
                    len(messages),
                )

            return Session(
                key=key,
                messages=messages,
                created_at=(
                    datetime.fromisoformat(meta["created_at"])
                    if meta.get("created_at")
                    else datetime.now()
                ),
                updated_at=(
                    datetime.fromisoformat(meta["updated_at"])
                    if meta.get("updated_at")
                    else datetime.now()
                ),
                metadata=json.loads(meta.get("metadata_json") or "{}"),
                last_consolidated=meta.get("last_consolidated", 0),
            )
        except Exception as e:
            logger.warning("⚠️ 会话加载失败 / load failed: {} — {}", key, e)
            return None

    def get_tail_messages(self, key: str, limit: int) -> list[dict[str, Any]]:
        """Get last N messages without loading full session (fast path for display)."""
        import os
        import time

        cached = self._cache.get(key)
        if cached is not None:
            max_messages = limit if limit > 0 else 500
            return cached.get_display_history(max_messages=max_messages)

        _profile = os.getenv("BAO_DESKTOP_PROFILE") == "1"
        t0 = time.perf_counter() if _profile else 0
        safe = _escape(key)
        where_clause = f"session_key = '{safe}'"
        try:
            if limit > 0:
                total = self._msg_tbl.count_rows(filter=where_clause)
                if total <= 0:
                    return []
                start_idx = max(total - limit, 0)
                where_clause = f"{where_clause} AND idx >= {start_idx}"

            msg_rows = self._msg_tbl.search().where(where_clause).to_list()
            if not msg_rows:
                return []
            msg_rows.sort(key=lambda r: r["idx"])
            if limit > 0:
                msg_rows = msg_rows[-limit:]
            t1 = time.perf_counter() if _profile else 0
            messages = []
            for r in msg_rows:
                m: dict[str, Any] = {
                    "role": r["role"],
                    "content": r["content"],
                    "timestamp": r["timestamp"],
                }
                extra_json = r.get("extra_json") or "{}"
                if extra_json != "{}":
                    m.update(json.loads(extra_json))
                messages.append(m)
            t2 = time.perf_counter() if _profile else 0
            if _profile:
                logger.debug(
                    "📊 get_tail_messages: fetch={:.3f}s, parse={:.3f}s, count={}",
                    t1 - t0,
                    t2 - t1,
                    len(messages),
                )
            return messages
        except Exception as e:
            logger.warning("⚠️ get_tail_messages failed: {} — {}", key, e)
            return []

    def save(self, session: Session) -> None:
        safe = _escape(session.key)
        prev_meta: list[dict[str, Any]] = []
        prev_msgs: list[dict[str, Any]] = []
        try:
            prev_meta = self._meta_tbl.search().where(f"session_key = '{safe}'").limit(1).to_list()
        except Exception:
            prev_meta = []
        try:
            prev_msgs = self._msg_tbl.search().where(f"session_key = '{safe}'").to_list()
        except Exception:
            prev_msgs = []

        try:
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
                    extra = {
                        k: v for k, v in msg.items() if k not in ("role", "content", "timestamp")
                    }
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
        except Exception:
            try:
                self._meta_tbl.delete(f"session_key = '{safe}'")
            except Exception:
                pass
            try:
                self._msg_tbl.delete(f"session_key = '{safe}'")
            except Exception:
                pass
            if prev_meta:
                self._meta_tbl.add(prev_meta)
            if prev_msgs:
                self._msg_tbl.add(prev_msgs)
            raise

        self._cache[session.key] = session

    def update_metadata_only(self, key: str, metadata_updates: dict[str, Any]) -> None:
        """Update session metadata without loading/saving messages (lightweight)."""
        safe = _escape(key)
        try:
            meta_rows = self._meta_tbl.search().where(f"session_key = '{safe}'").limit(1).to_list()
            if not meta_rows:
                return
            meta = meta_rows[0]
            current_metadata = json.loads(meta.get("metadata_json") or "{}")
            current_metadata.update(metadata_updates)
            self._meta_tbl.delete(f"session_key = '{safe}'")
            self._meta_tbl.add(
                [
                    {
                        "session_key": key,
                        "created_at": meta["created_at"],
                        "updated_at": meta["updated_at"],
                        "metadata_json": json.dumps(current_metadata, ensure_ascii=False),
                        "last_consolidated": meta.get("last_consolidated", 0),
                    }
                ]
            )
            if key in self._cache:
                self._cache[key].metadata.update(metadata_updates)
        except Exception as e:
            logger.warning("⚠️ metadata update failed: {} — {}", key, e)

    def invalidate(self, key: str) -> None:
        self._cache.pop(key, None)

    def _delete_meta_row(self, key: str) -> bool:
        try:
            self._meta_tbl.delete(f"session_key = '{_escape(key)}'")
            return True
        except Exception:
            return False

    def delete_session(self, key: str) -> bool:
        safe = _escape(key)
        prev_meta: list[dict[str, Any]] = []
        prev_msgs: list[dict[str, Any]] = []
        try:
            prev_meta = self._meta_tbl.search().where(f"session_key = '{safe}'").limit(1).to_list()
        except Exception:
            prev_meta = []
        try:
            prev_msgs = self._msg_tbl.search().where(f"session_key = '{safe}'").to_list()
        except Exception:
            prev_msgs = []

        ok = self._delete_meta_row(key)
        try:
            self._msg_tbl.delete(f"session_key = '{safe}'")
        except Exception:
            ok = False
        if not ok:
            try:
                self._meta_tbl.delete(f"session_key = '{safe}'")
            except Exception:
                pass
            try:
                self._msg_tbl.delete(f"session_key = '{safe}'")
            except Exception:
                pass
            if prev_meta:
                try:
                    self._meta_tbl.add(prev_meta)
                except Exception:
                    pass
            if prev_msgs:
                try:
                    self._msg_tbl.add(prev_msgs)
                except Exception:
                    pass
            self._cache.pop(key, None)
            return False
        self._cache.pop(key, None)
        # Defensive: clear _active_cache if it points to the deleted session
        for nk, ak in list(self._active_cache.items()):
            if ak == key:
                self._active_cache.pop(nk, None)
        try:
            rows = self._meta_tbl.search().where("session_key != '_init_'").to_list()
            for row in rows:
                session_key = str(row.get("session_key", ""))
                if not session_key.startswith("_active:"):
                    continue
                natural_key = session_key[len("_active:") :]
                active_key = json.loads(row.get("metadata_json") or "{}").get("active_key")
                if active_key == key:
                    if not self._delete_meta_row(session_key):
                        ok = False
                    self._active_cache.pop(natural_key, None)
        except Exception:
            ok = False
        try:
            from bao.agent.artifacts import ArtifactStore

            ArtifactStore(self.workspace, key, 0).cleanup_session()
        except Exception:
            pass
        return ok

    def get_active_session_key(self, natural_key: str) -> str | None:
        if natural_key in self._active_cache:
            return self._active_cache[natural_key]
        safe = _escape(f"_active:{natural_key}")
        try:
            rows = self._meta_tbl.search().where(f"session_key = '{safe}'").to_list()
            if rows:
                rows.sort(key=lambda row: str(row.get("updated_at", "")), reverse=True)
                for row in rows:
                    try:
                        val = json.loads(row.get("metadata_json") or "{}").get("active_key")
                    except Exception:
                        continue
                    if val:
                        self._active_cache[natural_key] = val
                        return val
        except Exception:
            pass
        return None

    def set_active_session_key(self, natural_key: str, session_key: str) -> None:
        self._active_cache[natural_key] = session_key
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
        self._active_cache.pop(natural_key, None)
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
