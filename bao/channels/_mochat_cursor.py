"""Mochat cursor persistence helpers."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime

from loguru import logger

from ._mochat_common import CURSOR_SAVE_DEBOUNCE_S


class _MochatCursorMixin:
    def _migrate_legacy_session_cursors(self) -> None:
        legacy_path = self._legacy_cursor_path
        if not legacy_path.exists():
            return
        try:
            if self._cursor_path.exists():
                legacy_path.unlink()
            else:
                self._state_dir.mkdir(parents=True, exist_ok=True)
                legacy_path.replace(self._cursor_path)
            try:
                legacy_path.parent.rmdir()
            except OSError:
                pass
        except Exception as exc:
            logger.debug("ℹ️ Mochat 游标迁移失败 / cursor migration failed: {}", exc)

    def _mark_session_cursor(self, session_id: str, cursor: int) -> None:
        if cursor < 0 or cursor < self._session_cursor.get(session_id, 0):
            return
        self._session_cursor[session_id] = cursor
        if not self._cursor_save_task or self._cursor_save_task.done():
            self._cursor_save_task = asyncio.create_task(self._save_cursor_debounced())

    async def _save_cursor_debounced(self) -> None:
        await asyncio.sleep(CURSOR_SAVE_DEBOUNCE_S)
        await self._save_session_cursors()

    async def _load_session_cursors(self) -> None:
        self._migrate_legacy_session_cursors()
        if not self._cursor_path.exists():
            return
        try:
            data = json.loads(self._cursor_path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.debug("ℹ️ Mochat 游标读取失败 / cursor read failed: {}", exc)
            return
        cursors = data.get("cursors") if isinstance(data, dict) else None
        if isinstance(cursors, dict):
            for session_id, cursor in cursors.items():
                if isinstance(session_id, str) and isinstance(cursor, int) and cursor >= 0:
                    self._session_cursor[session_id] = cursor

    async def _save_session_cursors(self) -> None:
        try:
            self._state_dir.mkdir(parents=True, exist_ok=True)
            self._cursor_path.write_text(
                json.dumps(
                    {
                        "schemaVersion": 1,
                        "updatedAt": datetime.utcnow().isoformat(),
                        "cursors": self._session_cursor,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
        except Exception as exc:
            logger.debug("ℹ️ Mochat 游标保存失败 / cursor save failed: {}", exc)
