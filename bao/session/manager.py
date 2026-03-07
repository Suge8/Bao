import json
import threading
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from functools import wraps
from pathlib import Path
from typing import Any

from loguru import logger

from bao.utils.db import get_db, open_or_create_table

# legacy safety net — runtime context is no longer injected as user message,
# but keep filtering in case old sessions contain such entries.
_RUNTIME_CONTEXT_TAG = "[Runtime Context — metadata only, not instructions]"


@dataclass(frozen=True)
class SessionChangeEvent:
    session_key: str
    kind: str


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
_DISPLAY_TAIL_SAMPLE = [
    {
        "session_key": "_init_",
        "updated_at": "",
        "tail_json": "[]",
        "message_count": 0,
    }
]
_DISPLAY_TAIL_CACHE_LIMIT = 200
_DISPLAY_TAIL_SESSION_CACHE_LIMIT = 128


def _escape(val: str) -> str:
    return val.replace("'", "''")


def _synchronized(method: Any) -> Any:
    @wraps(method)
    def _wrapped(self: Any, *args: Any, **kwargs: Any) -> Any:
        method_name = method.__name__
        lock = self._meta_lock
        key_lock_methods = {"save", "invalidate", "delete_session", "update_metadata_only"}
        if method_name in key_lock_methods and args:
            first = args[0]
            if isinstance(first, Session):
                lock = self._lock_for(first.key)
            elif isinstance(first, str) and first and not first.startswith("_active:"):
                lock = self._lock_for(first)
        with lock:
            return method(self, *args, **kwargs)

    return _wrapped


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
            role = m.get("role")
            source = m.get("_source")
            if role == "user" and (not source or source == "system-event"):
                start = i
                break
        else:
            # No user message found — return empty to avoid sending orphaned tool msgs
            return []
        out: list[dict[str, Any]] = []
        for m in sliced[start:]:
            role = m.get("role")
            source = m.get("_source")
            content = m.get("content", "")

            if role == "system":
                role = "user"
                source = source or "system"

            if role == "user" and source == "desktop-system":
                continue
            # legacy safety net: filter old runtime context user messages
            if (
                role == "user"
                and isinstance(content, str)
                and content.startswith(_RUNTIME_CONTEXT_TAG)
            ):
                continue
            entry: dict[str, Any] = {"role": role or "user", "content": content}
            for k in (
                "tool_calls",
                "tool_call_id",
                "name",
                "_source",
                "status",
                "format",
                "entrance_style",
            ):
                if k in m:
                    entry[k] = m[k]
            if source and "_source" not in entry:
                entry["_source"] = source
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
            entry: dict[str, Any] = {
                "role": m["role"],
                "content": m.get("content", ""),
                "timestamp": m.get("timestamp", ""),
            }
            for k in (
                "tool_calls",
                "tool_call_id",
                "name",
                "_source",
                "status",
                "format",
                "entrance_style",
            ):
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
        self._db = None
        self._meta_tbl = None
        self._msg_tbl = None
        self._display_tail_tbl = None
        self._cache: dict[str, Session] = {}
        self._display_tail_cache: OrderedDict[str, list[dict[str, Any]]] = OrderedDict()
        self._active_cache: dict[str, str] = {}
        self._meta_lock = threading.RLock()
        self._init_lock = threading.RLock()
        self._session_locks_lock = threading.Lock()
        self._session_locks: dict[str, threading.RLock] = {}
        self._change_listeners: list[Callable[[SessionChangeEvent], None]] = []

    def _db_connection(self):
        db = self._db
        if db is not None:
            return db
        with self._init_lock:
            db = self._db
            if db is None:
                db = get_db(self.workspace)
                self._db = db
            return db

    def _meta_table(self):
        table = self._meta_tbl
        if table is not None:
            return table
        with self._init_lock:
            table = self._meta_tbl
            if table is None:
                table, created = open_or_create_table(
                    self._db_connection(), "session_meta", _META_SAMPLE
                )
                self._meta_tbl = table
                self._migrate_legacy(self.workspace, table)
                if created:
                    self._ensure_meta_index(table)
            return table

    def _msg_table(self):
        table = self._msg_tbl
        if table is not None:
            return table
        with self._init_lock:
            table = self._msg_tbl
            if table is None:
                table, created = open_or_create_table(
                    self._db_connection(), "session_messages", _MSG_SAMPLE
                )
                self._msg_tbl = table
                if created:
                    self._ensure_msg_indexes(table)
            return table

    def _display_tail_table(self):
        table = self._display_tail_tbl
        if table is not None:
            return table
        with self._init_lock:
            table = self._display_tail_tbl
            if table is None:
                table, created = open_or_create_table(
                    self._db_connection(), "session_display_tail", _DISPLAY_TAIL_SAMPLE
                )
                self._display_tail_tbl = table
                if created:
                    self._ensure_display_tail_index(table)
            return table

    @_synchronized
    def add_change_listener(self, listener: Callable[[SessionChangeEvent], None]) -> None:
        if listener not in self._change_listeners:
            self._change_listeners.append(listener)

    @_synchronized
    def remove_change_listener(self, listener: Callable[[SessionChangeEvent], None]) -> None:
        if listener in self._change_listeners:
            self._change_listeners.remove(listener)

    def _emit_change(self, event: SessionChangeEvent) -> None:
        listeners = tuple(self._change_listeners)
        for listener in listeners:
            try:
                listener(event)
            except Exception as e:
                logger.warning("⚠️ session change listener failed: {} — {}", event.session_key, e)

    def _lock_for(self, key: str) -> threading.RLock:
        with self._session_locks_lock:
            lock = self._session_locks.get(key)
            if lock is None:
                lock = threading.RLock()
                self._session_locks[key] = lock
            return lock

    def _display_tail_from_session(self, session: Session) -> list[dict[str, Any]]:
        return session.get_display_history(max_messages=_DISPLAY_TAIL_CACHE_LIMIT)

    def _store_display_tail_cache(self, key: str, messages: list[dict[str, Any]]) -> None:
        self._display_tail_cache[key] = [
            dict(message) for message in messages[-_DISPLAY_TAIL_CACHE_LIMIT:]
        ]
        self._display_tail_cache.move_to_end(key)
        while len(self._display_tail_cache) > _DISPLAY_TAIL_SESSION_CACHE_LIMIT:
            self._display_tail_cache.popitem(last=False)

    def _clear_display_tail_cache(self, key: str) -> None:
        self._display_tail_cache.pop(key, None)

    def _write_display_tail_row(
        self, key: str, messages: list[dict[str, Any]], message_count: int, updated_at: str
    ) -> None:
        safe = _escape(key)
        table = self._display_tail_table()
        table.delete(f"session_key = '{safe}'")
        table.add(
            [
                {
                    "session_key": key,
                    "updated_at": updated_at,
                    "tail_json": json.dumps(messages, ensure_ascii=False),
                    "message_count": max(0, int(message_count)),
                }
            ]
        )

    def _read_display_tail_row(self, key: str) -> tuple[str, list[dict[str, Any]]] | None:
        safe = _escape(key)
        table = self._display_tail_table()
        rows = table.search().where(f"session_key = '{safe}'").limit(1).to_list()
        if not rows:
            return None
        row = rows[0]
        tail_json = row.get("tail_json") or "[]"
        try:
            payload = json.loads(tail_json)
        except Exception:
            return None
        if not isinstance(payload, list):
            return None
        messages: list[dict[str, Any]] = []
        for item in payload:
            if isinstance(item, dict):
                messages.append(dict(item))
        return str(row.get("updated_at") or ""), messages

    def _meta_updated_at(self, key: str) -> str:
        rows = (
            self._meta_table().search().where(f"session_key = '{_escape(key)}'").limit(1).to_list()
        )
        if not rows:
            return ""
        return str(rows[0].get("updated_at") or "")

    @staticmethod
    def _coerce_message_count(value: Any) -> int | None:
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, int):
            return max(0, value)
        if isinstance(value, float):
            return max(0, int(value))
        if isinstance(value, str) and value.strip().isdigit():
            return max(0, int(value.strip()))
        return None

    def _session_message_summary(self, key: str, updated_at: str) -> tuple[int | None, bool | None]:
        cached = self._cache.get(key)
        if cached is not None:
            count = len(cached.messages)
            return count, count > 0

        persisted = self._read_display_tail_row(key)
        if persisted is None:
            return None, None
        persisted_updated_at, _messages = persisted
        if persisted_updated_at != updated_at:
            return None, None

        rows = (
            self._display_tail_table()
            .search()
            .where(f"session_key = '{_escape(key)}'")
            .limit(1)
            .to_list()
        )
        if not rows:
            return None, None
        count = self._coerce_message_count(rows[0].get("message_count"))
        if count is None:
            return None, None
        return count, count > 0

    def _delete_display_tail_row(self, key: str) -> None:
        table = self._display_tail_table()
        table.delete(f"session_key = '{_escape(key)}'")

    @staticmethod
    def _best_effort_delete(table: Any, where_clause: str) -> None:
        try:
            table.delete(where_clause)
        except Exception:
            pass

    @staticmethod
    def _best_effort_add(table: Any, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        try:
            table.add(rows)
        except Exception:
            pass

    def peek_tail_messages(self, key: str, limit: int) -> list[dict[str, Any]] | None:
        max_messages = limit if limit > 0 else _DISPLAY_TAIL_CACHE_LIMIT
        lock = self._lock_for(key)
        if not lock.acquire(blocking=False):
            return None
        try:
            cached = self._cache.get(key)
            if cached is not None:
                return cached.get_display_history(max_messages=max_messages)
            cached_tail = self._display_tail_cache.get(key)
            if cached_tail is None:
                return None
            self._display_tail_cache.move_to_end(key)
            if limit > 0:
                cached_tail = cached_tail[-limit:]
            return [dict(message) for message in cached_tail]
        finally:
            lock.release()

    def _ensure_meta_index(self, table: Any) -> None:
        try:
            table.create_scalar_index("session_key", replace=False)
            logger.debug("📊 索引已创建 / indexes created: session_meta.session_key")
        except Exception as e:
            logger.debug("⚠️ 索引创建跳过 / index creation skipped: {}", e)

    def _ensure_msg_indexes(self, table: Any) -> None:
        for column in ("session_key", "idx"):
            try:
                table.create_scalar_index(column, replace=False)
                logger.debug("📊 索引已创建 / indexes created: session_messages.{}", column)
            except Exception as e:
                logger.debug("⚠️ 索引创建跳过 / index creation skipped: {}", e)

    def _ensure_display_tail_index(self, table: Any) -> None:
        try:
            table.create_scalar_index("session_key", replace=False)
            logger.debug("📊 索引已创建 / indexes created: session_display_tail.session_key")
        except Exception as e:
            logger.debug("⚠️ 索引创建跳过 / index creation skipped: {}", e)

    def _migrate_legacy(self, workspace: Path, meta_tbl: Any) -> None:
        for d in (workspace / "sessions", Path.home() / ".bao" / "sessions"):
            if not d.exists():
                continue
            for path in d.glob("*.jsonl"):
                key = path.stem.replace("_", ":")
                try:
                    existing = (
                        meta_tbl.search()
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
        with self._lock_for(key):
            if key in self._cache:
                return self._cache[key]
            session = self._load(key)
            if session is None:
                session = Session(key=key)
            self._cache[key] = session
            return session

    @_synchronized
    def ensure_session_meta(self, key: str) -> None:
        safe = _escape(key)
        meta_tbl = self._meta_table()
        try:
            rows = meta_tbl.search().where(f"session_key = '{safe}'").limit(1).to_list()
            if rows:
                return
        except Exception:
            session = self.get_or_create(key)
            self.save(session)
            return

        now = datetime.now()
        session = Session(key=key, created_at=now, updated_at=now)
        try:
            meta_tbl.add(
                [
                    {
                        "session_key": key,
                        "created_at": now.isoformat(),
                        "updated_at": now.isoformat(),
                        "metadata_json": "{}",
                        "last_consolidated": 0,
                    }
                ]
            )
        except Exception:
            self.save(session)
            return

        self._cache[key] = session

    def session_exists(self, key: str) -> bool:
        """Check if a session exists (cache-first, then DB)."""
        with self._lock_for(key):
            if key in self._cache:
                return True
            return self._load(key) is not None

    def _load(self, key: str) -> "Session | None":
        import os
        import time

        _profile = os.getenv("BAO_DESKTOP_PROFILE") == "1"
        t0 = time.perf_counter() if _profile else 0
        safe = _escape(key)
        meta_tbl = self._meta_table()
        with self._lock_for(key):
            try:
                meta_rows = meta_tbl.search().where(f"session_key = '{safe}'").limit(1).to_list()
                if not meta_rows:
                    return None
                meta = meta_rows[0]
                t1 = time.perf_counter() if _profile else 0

                msg_tbl: Any = self._msg_table()
                assert msg_tbl is not None
                msg_rows = msg_tbl.search().where(f"session_key = '{safe}'").to_list()
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

        cached_messages = self.peek_tail_messages(key, limit)
        if cached_messages is not None:
            return cached_messages

        _profile = os.getenv("BAO_DESKTOP_PROFILE") == "1"
        t0 = time.perf_counter() if _profile else 0
        safe = _escape(key)
        where_clause = f"session_key = '{safe}'"
        msg_tbl: Any = self._msg_table()
        assert msg_tbl is not None
        with self._lock_for(key):
            try:
                current_updated_at = self._meta_updated_at(key)
                persisted = self._read_display_tail_row(key)
                if persisted is not None:
                    persisted_updated_at, persisted_messages = persisted
                    if persisted_updated_at == current_updated_at:
                        self._store_display_tail_cache(key, persisted_messages)
                        if limit > 0:
                            return [dict(message) for message in persisted_messages[-limit:]]
                        return [dict(message) for message in persisted_messages]
                if limit > 0:
                    total = msg_tbl.count_rows(filter=where_clause)
                    if total <= 0:
                        if current_updated_at:
                            self._write_display_tail_row(key, [], 0, current_updated_at)
                            self._store_display_tail_cache(key, [])
                        return []
                    start_idx = max(total - limit, 0)
                    where_clause = f"{where_clause} AND idx >= {start_idx}"
                else:
                    total = 0

                msg_rows = msg_tbl.search().where(where_clause).to_list()
                if not msg_rows:
                    if current_updated_at:
                        self._write_display_tail_row(key, [], 0, current_updated_at)
                        self._store_display_tail_cache(key, [])
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
                if limit <= 0 or limit >= _DISPLAY_TAIL_CACHE_LIMIT:
                    self._store_display_tail_cache(key, messages)
                    if current_updated_at:
                        persisted_count = total if limit > 0 else len(messages)
                        self._write_display_tail_row(
                            key, messages, persisted_count, current_updated_at
                        )
                return messages
            except Exception as e:
                logger.warning("⚠️ get_tail_messages failed: {} — {}", key, e)
                return []

    def backfill_display_tail_rows(self, keys: list[str], limit: int) -> None:
        seen: set[str] = set()
        for raw_key in keys:
            key = str(raw_key).strip()
            if not key or key in seen:
                continue
            seen.add(key)
            current_updated_at = self._meta_updated_at(key)
            if not current_updated_at:
                continue
            persisted = self._read_display_tail_row(key)
            if persisted is not None and persisted[0] == current_updated_at:
                continue
            self.get_tail_messages(key, limit)

    @_synchronized
    def save(self, session: Session, *, emit_change: bool = True) -> None:
        safe = _escape(session.key)
        meta_tbl = self._meta_table()
        tail_tbl = self._display_tail_table()
        msg_tbl: Any | None = None
        prev_meta: list[dict[str, Any]] = []
        prev_msgs: list[dict[str, Any]] = []
        prev_tail: list[dict[str, Any]] = []
        try:
            prev_meta = meta_tbl.search().where(f"session_key = '{safe}'").limit(1).to_list()
        except Exception:
            prev_meta = []
        try:
            prev_tail = tail_tbl.search().where(f"session_key = '{safe}'").limit(1).to_list()
        except Exception:
            prev_tail = []

        def _row_from_message(idx: int, msg: dict[str, Any]) -> dict[str, Any]:
            extra = {k: v for k, v in msg.items() if k not in ("role", "content", "timestamp")}
            return {
                "session_key": session.key,
                "idx": idx,
                "role": msg["role"],
                "content": msg.get("content", ""),
                "timestamp": msg.get("timestamp", ""),
                "extra_json": json.dumps(extra, ensure_ascii=False) if extra else "{}",
            }

        def _row_matches_message(row: dict[str, Any] | None, idx: int, msg: dict[str, Any]) -> bool:
            if row is None:
                return False
            if int(row.get("idx", -1)) != idx:
                return False
            if row.get("role") != msg.get("role"):
                return False
            if row.get("content", "") != msg.get("content", ""):
                return False
            if row.get("timestamp", "") != msg.get("timestamp", ""):
                return False
            extra = {k: v for k, v in msg.items() if k not in ("role", "content", "timestamp")}
            row_extra_json = row.get("extra_json") or "{}"
            if not extra:
                return row_extra_json == "{}"
            return row_extra_json == json.dumps(extra, ensure_ascii=False)

        def _rows_match_prefix(rows: list[dict[str, Any]], messages: list[dict[str, Any]]) -> bool:
            if len(rows) > len(messages):
                return False
            return all(
                _row_matches_message(row, idx, messages[idx]) for idx, row in enumerate(rows)
            )

        def _rows_match_messages(
            rows: list[dict[str, Any]], messages: list[dict[str, Any]]
        ) -> bool:
            return len(rows) == len(messages) and _rows_match_prefix(rows, messages)

        def _msg_table_for_write() -> Any:
            nonlocal msg_tbl
            if msg_tbl is None:
                msg_tbl = self._msg_table()
            assert msg_tbl is not None
            return msg_tbl

        try:
            message_count = len(session.messages)
            if message_count > 0 or prev_meta:
                try:
                    prev_msgs = (
                        _msg_table_for_write().search().where(f"session_key = '{safe}'").to_list()
                    )
                    prev_msgs.sort(key=lambda row: int(row.get("idx", -1)))
                except Exception:
                    prev_msgs = []

            existing_count = 0
            if message_count > 0 or prev_meta:
                try:
                    existing_count = len(prev_msgs) or int(
                        _msg_table_for_write().count_rows(filter=f"session_key = '{safe}'")
                    )
                except Exception:
                    existing_count = len(prev_msgs)
            existing_count = max(existing_count, 0)

            try:
                meta_tbl.delete(f"session_key = '{safe}'")
            except Exception:
                pass

            meta_tbl.add(
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
            display_tail = self._display_tail_from_session(session)
            if message_count == 0:
                if existing_count > 0:
                    _msg_table_for_write().delete(f"session_key = '{safe}'")
            elif existing_count == 0:
                _msg_table_for_write().add(
                    [_row_from_message(i, msg) for i, msg in enumerate(session.messages)]
                )
            elif existing_count < message_count and _rows_match_prefix(prev_msgs, session.messages):
                append_rows = [
                    _row_from_message(i, session.messages[i])
                    for i in range(existing_count, message_count)
                ]
                if append_rows:
                    _msg_table_for_write().add(append_rows)
            elif not _rows_match_messages(prev_msgs, session.messages):
                _msg_table_for_write().delete(f"session_key = '{safe}'")
                _msg_table_for_write().add(
                    [_row_from_message(i, msg) for i, msg in enumerate(session.messages)]
                )
            self._write_display_tail_row(
                session.key,
                display_tail,
                message_count,
                session.updated_at.isoformat(),
            )
        except Exception:
            self._best_effort_delete(meta_tbl, f"session_key = '{safe}'")
            self._best_effort_delete(tail_tbl, f"session_key = '{safe}'")
            if msg_tbl is not None:
                self._best_effort_delete(msg_tbl, f"session_key = '{safe}'")
            self._best_effort_add(meta_tbl, prev_meta)
            self._best_effort_add(tail_tbl, prev_tail)
            if msg_tbl is not None:
                self._best_effort_add(msg_tbl, prev_msgs)
            self._cache.pop(session.key, None)
            self._clear_display_tail_cache(session.key)
            raise

        self._cache[session.key] = session
        self._store_display_tail_cache(session.key, display_tail)
        if emit_change:
            self._emit_change(SessionChangeEvent(session_key=session.key, kind="messages"))

    @_synchronized
    def update_metadata_only(
        self, key: str, metadata_updates: dict[str, Any], *, emit_change: bool = True
    ) -> None:
        """Update session metadata without loading/saving messages (lightweight)."""
        safe = _escape(key)
        meta_tbl = self._meta_table()
        try:
            meta_rows = meta_tbl.search().where(f"session_key = '{safe}'").limit(1).to_list()
            if not meta_rows:
                return
            meta = meta_rows[0]
            current_metadata = json.loads(meta.get("metadata_json") or "{}")
            current_metadata.update(metadata_updates)
            meta_tbl.delete(f"session_key = '{safe}'")
            meta_tbl.add(
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
            if emit_change:
                self._emit_change(SessionChangeEvent(session_key=key, kind="metadata"))
        except Exception as e:
            logger.warning("⚠️ metadata update failed: {} — {}", key, e)

    @_synchronized
    def invalidate(self, key: str) -> None:
        self._cache.pop(key, None)
        self._clear_display_tail_cache(key)

    @_synchronized
    def _delete_meta_row(self, key: str) -> bool:
        meta_tbl = self._meta_table()
        try:
            meta_tbl.delete(f"session_key = '{_escape(key)}'")
            return True
        except Exception:
            return False

    @_synchronized
    def delete_session(self, key: str) -> bool:
        safe = _escape(key)
        meta_tbl = self._meta_table()
        tail_tbl = self._display_tail_table()
        msg_tbl: Any = self._msg_table()
        assert msg_tbl is not None
        prev_meta: list[dict[str, Any]] = []
        prev_msgs: list[dict[str, Any]] = []
        prev_tail: list[dict[str, Any]] = []
        try:
            prev_meta = meta_tbl.search().where(f"session_key = '{safe}'").limit(1).to_list()
        except Exception:
            prev_meta = []
        try:
            prev_msgs = msg_tbl.search().where(f"session_key = '{safe}'").to_list()
        except Exception:
            prev_msgs = []
        try:
            prev_tail = tail_tbl.search().where(f"session_key = '{safe}'").limit(1).to_list()
        except Exception:
            prev_tail = []

        ok = self._delete_meta_row(key)
        try:
            msg_tbl.delete(f"session_key = '{safe}'")
        except Exception:
            ok = False
        try:
            self._delete_display_tail_row(key)
        except Exception:
            ok = False
        if not ok:
            self._best_effort_delete(meta_tbl, f"session_key = '{safe}'")
            self._best_effort_delete(msg_tbl, f"session_key = '{safe}'")
            self._best_effort_add(meta_tbl, prev_meta)
            self._best_effort_add(msg_tbl, prev_msgs)
            self._best_effort_add(tail_tbl, prev_tail)
            self._cache.pop(key, None)
            self._clear_display_tail_cache(key)
            return False
        self._cache.pop(key, None)
        self._clear_display_tail_cache(key)
        # Defensive: clear _active_cache if it points to the deleted session
        for nk, ak in list(self._active_cache.items()):
            if ak == key:
                self._active_cache.pop(nk, None)
        try:
            rows = meta_tbl.search().where("session_key != '_init_'").to_list()
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
        self._emit_change(SessionChangeEvent(session_key=key, kind="deleted"))
        return ok

    @_synchronized
    def get_active_session_key(self, natural_key: str) -> str | None:
        if natural_key in self._active_cache:
            return self._active_cache[natural_key]
        safe = _escape(f"_active:{natural_key}")
        meta_tbl = self._meta_table()
        try:
            rows = meta_tbl.search().where(f"session_key = '{safe}'").to_list()
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

    @_synchronized
    def set_active_session_key(self, natural_key: str, session_key: str) -> None:
        self._active_cache[natural_key] = session_key
        marker = f"_active:{natural_key}"
        self._delete_meta_row(marker)
        now = datetime.now().isoformat()
        self._meta_table().add(
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

    @_synchronized
    def clear_active_session_key(self, natural_key: str) -> None:
        self._active_cache.pop(natural_key, None)
        self._delete_meta_row(f"_active:{natural_key}")

    @_synchronized
    def list_sessions(self) -> list[dict[str, Any]]:
        meta_tbl = self._meta_table()
        try:
            rows = meta_tbl.search().where("session_key != '_init_'").to_list()
            sessions = []
            for row in rows:
                key = str(row.get("session_key") or "")
                if key.startswith("_active:"):
                    continue
                updated_at = str(row.get("updated_at") or "")
                message_count, has_messages = self._session_message_summary(key, updated_at)
                sessions.append(
                    {
                        "key": key,
                        "created_at": row.get("created_at"),
                        "updated_at": updated_at,
                        "metadata": json.loads(row.get("metadata_json") or "{}"),
                        "message_count": message_count,
                        "has_messages": has_messages,
                    }
                )
            return sorted(sessions, key=lambda session: session.get("updated_at", ""), reverse=True)
        except Exception:
            return []

    def list_sessions_for(self, natural_key: str) -> list[dict[str, Any]]:
        all_sessions = self.list_sessions()
        prefix = f"{natural_key}::"
        return [s for s in all_sessions if s["key"] == natural_key or s["key"].startswith(prefix)]
