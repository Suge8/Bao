from __future__ import annotations

import json

from loguru import logger

from bao.session.state import canonicalize_persisted_metadata, nest_flat_persisted_metadata, split_runtime_metadata

from ._manager_models import _DISPLAY_TAIL_SAMPLE, _META_SAMPLE, _MSG_SAMPLE, escape_sql_value


class SessionManagerTablesMixin:
    def _db_connection(self):
        if self._db is not None:
            return self._db
        with self._init_lock:
            if self._db is None:
                from bao.session import manager as manager_module

                self._db = manager_module.get_db(self.workspace)
            return self._db

    def _meta_table(self):
        if self._meta_tbl is not None:
            return self._meta_tbl
        with self._init_lock:
            if self._meta_tbl is None:
                from bao.session import manager as manager_module

                table, created = manager_module.open_or_create_table(self._db_connection(), "session_meta", _META_SAMPLE)
                self._meta_tbl = table
                self._migrate_metadata_schema(table)
                if created:
                    self._ensure_meta_index(table)
            return self._meta_tbl

    def _msg_table(self):
        if self._msg_tbl is not None:
            return self._msg_tbl
        with self._init_lock:
            if self._msg_tbl is None:
                from bao.session import manager as manager_module

                table, created = manager_module.open_or_create_table(
                    self._db_connection(),
                    "session_messages",
                    _MSG_SAMPLE,
                )
                self._msg_tbl = table
                if created:
                    self._ensure_msg_indexes(table)
            return self._msg_tbl

    def _display_tail_table(self):
        if self._display_tail_tbl is not None:
            return self._display_tail_tbl
        with self._init_lock:
            if self._display_tail_tbl is None:
                from bao.session import manager as manager_module

                table, created = manager_module.open_or_create_table(
                    self._db_connection(),
                    "session_display_tail",
                    _DISPLAY_TAIL_SAMPLE,
                )
                self._display_tail_tbl = table
                if created:
                    self._ensure_display_tail_index(table)
            return self._display_tail_tbl

    @staticmethod
    def _ensure_meta_index(table) -> None:
        try:
            table.create_scalar_index("session_key", replace=False)
            logger.debug("📊 索引已创建 / indexes created: session_meta.session_key")
        except Exception as exc:
            logger.debug("⚠️ 索引创建跳过 / index creation skipped: {}", exc)

    @staticmethod
    def _ensure_msg_indexes(table) -> None:
        for column in ("session_key", "idx"):
            try:
                table.create_scalar_index(column, replace=False)
                logger.debug("📊 索引已创建 / indexes created: session_messages.{}", column)
            except Exception as exc:
                logger.debug("⚠️ 索引创建跳过 / index creation skipped: {}", exc)

    @staticmethod
    def _ensure_display_tail_index(table) -> None:
        try:
            table.create_scalar_index("session_key", replace=False)
            logger.debug("📊 索引已创建 / indexes created: session_display_tail.session_key")
        except Exception as exc:
            logger.debug("⚠️ 索引创建跳过 / index creation skipped: {}", exc)

    def _migrate_metadata_schema(self, meta_tbl) -> None:
        try:
            rows = meta_tbl.search().where("session_key != '_init_'").to_list()
        except Exception:
            return
        for row in rows:
            session_key = str(row.get("session_key") or "")
            if not session_key or session_key.startswith("_active:"):
                continue
            raw_json = str(row.get("metadata_json") or "{}")
            try:
                persisted, _ = split_runtime_metadata(json.loads(raw_json))
            except Exception:
                continue
            canonical = (
                canonicalize_persisted_metadata(persisted)
                if any(key in persisted for key in ("routing", "workflow", "view"))
                else nest_flat_persisted_metadata(persisted)
            )
            canonical_json = json.dumps(canonical, ensure_ascii=False)
            if canonical_json == raw_json:
                continue
            try:
                meta_tbl.delete(f"session_key = '{escape_sql_value(session_key)}'")
                meta_tbl.add([{
                    "session_key": session_key,
                    "created_at": row.get("created_at"),
                    "updated_at": row.get("updated_at"),
                    "metadata_json": canonical_json,
                    "last_consolidated": row.get("last_consolidated", 0),
                }])
            except Exception:
                logger.debug("Skip metadata schema migration for {}", session_key)
