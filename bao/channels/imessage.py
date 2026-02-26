"""iMessage channel — polls chat.db + sends via AppleScript."""

from __future__ import annotations

import asyncio
import sqlite3
import sys
import time
from pathlib import Path

from loguru import logger

from bao.bus.events import OutboundMessage
from bao.bus.queue import MessageBus
from bao.channels.base import BaseChannel
from bao.config.schema import IMessageConfig
from bao.channels.progress_text import ProgressBuffer

CHAT_DB = Path.home() / "Library" / "Messages" / "chat.db"
APPLE_EPOCH_OFFSET = 978307200


class IMessageChannel(BaseChannel):
    name = "imessage"

    def __init__(self, config: IMessageConfig, bus: MessageBus):
        super().__init__(config, bus)
        self.config: IMessageConfig = config
        self._last_rowid: int = 0
        self._poll_interval: float = config.poll_interval
        self._progress = ProgressBuffer(self._send_text)

    async def start(self) -> None:
        if not CHAT_DB.exists():
            logger.error("iMessage chat.db not found — need Full Disk Access")
            return
        self._running = True
        self._last_rowid = self._get_max_rowid()
        if self._last_rowid == 0:
            logger.warning(
                "iMessage: cannot read chat.db (ROWID=0). "
                "Grant Full Disk Access to your Python binary: "
                "System Settings → Privacy & Security → Full Disk Access → add {}",
                sys.executable,
            )
        logger.debug("iMessage channel started (polling from ROWID {})", self._last_rowid)
        while self._running:
            try:
                await self._poll()
            except Exception as e:
                logger.error("iMessage poll error: {}", e)
            await asyncio.sleep(self._poll_interval)

    async def stop(self) -> None:
        await self._progress.flush_all()
        self._running = False

    async def send(self, msg: OutboundMessage) -> None:
        meta = msg.metadata or {}
        await self._progress.handle(
            msg.chat_id,
            msg.content or "",
            is_progress=bool(meta.get("_progress")),
            is_tool_hint=bool(meta.get("_tool_hint")),
        )
        for file_path in msg.media or []:
            if Path(file_path).is_file():
                await self._send_file(msg.chat_id, file_path)
            else:
                logger.warning("iMessage media file not found: {}", file_path)

    async def _send_text(self, buddy: str, text: str) -> None:
        encoded = text.replace("\\", "\\\\").replace('"', '\\"')
        script = (
            f'tell application "Messages"\n'
            f"  set targetService to 1st account whose service type = iMessage\n"
            f'  set targetBuddy to buddy "{buddy}" of targetService\n'
            f'  send "{encoded}" to targetBuddy\n'
            f"end tell"
        )
        try:
            proc = await asyncio.create_subprocess_exec(
                "osascript",
                "-e",
                script,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()
            if proc.returncode != 0:
                logger.error("AppleScript send failed: {}", stderr.decode().strip())
        except Exception as e:
            logger.error("iMessage send error: {}", e)

    async def _send_file(self, buddy: str, file_path: str) -> None:
        """Send a file (image/doc) via AppleScript POSIX file."""
        escaped = file_path.replace('\\', '\\\\').replace('"', '\\"')
        script = (
            f'tell application "Messages"\n'
            f"  set targetService to 1st account whose service type = iMessage\n"
            f'  set targetBuddy to buddy "{buddy}" of targetService\n'
            f'  send POSIX file "{escaped}" to targetBuddy\n'
            f"end tell"
        )
        try:
            proc = await asyncio.create_subprocess_exec(
                "osascript",
                "-e",
                script,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()
            if proc.returncode != 0:
                logger.error("AppleScript send file failed: {}", stderr.decode().strip())
        except Exception as e:
            logger.error("iMessage send file error: {}", e)

    # ---- internal ----

    def _get_max_rowid(self) -> int:
        try:
            conn = sqlite3.connect(f"file:{CHAT_DB}?mode=ro", uri=True, timeout=5)
            cur = conn.execute("SELECT MAX(ROWID) FROM message")
            val = cur.fetchone()[0]
            conn.close()
            return val or 0
        except Exception:
            return 0

    async def _poll(self) -> None:
        rows = await asyncio.to_thread(self._query_new)
        if not rows:
            return
        rowids = [r[0] for r in rows]
        attachments = await asyncio.to_thread(self._query_attachments, rowids)
        for rowid, text, sender, chat_id in rows:
            self._last_rowid = max(self._last_rowid, rowid)
            media = attachments.get(rowid, [])
            if not text and not media:
                continue
            if not self.is_allowed(sender):
                continue
            await self._handle_message(
                sender_id=sender,
                chat_id=chat_id,
                content=text or "",
                media=media or None,
            )

    def _query_new(self) -> list[tuple[int, str, str, str]]:
        for attempt in range(3):
            try:
                conn = sqlite3.connect(f"file:{CHAT_DB}?mode=ro", uri=True, timeout=5)
                cur = conn.execute(
                    """
                    SELECT m.ROWID, m.text, h.id, c.chat_identifier
                    FROM message m
                    LEFT JOIN handle h ON m.handle_id = h.ROWID
                    LEFT JOIN chat_message_join cmj ON m.ROWID = cmj.message_id
                    LEFT JOIN chat c ON cmj.chat_id = c.ROWID
                    WHERE m.ROWID > ? AND m.is_from_me = 0
                      AND (m.text IS NOT NULL OR m.cache_has_attachments = 1)
                    ORDER BY m.ROWID ASC
                    """,
                    (self._last_rowid,),
                )
                rows = cur.fetchall()
                conn.close()
                return rows
            except sqlite3.OperationalError:
                if attempt < 2:
                    time.sleep(0.5)
        return []

    def _query_attachments(self, rowids: list[int]) -> dict[int, list[str]]:
        """Batch-query attachment file paths for a list of message ROWIDs."""
        if not rowids:
            return {}
        try:
            conn = sqlite3.connect(f"file:{CHAT_DB}?mode=ro", uri=True, timeout=5)
            placeholders = ",".join("?" * len(rowids))
            cur = conn.execute(
                f"""
                SELECT maj.message_id, a.filename
                FROM message_attachment_join maj
                JOIN attachment a ON maj.attachment_id = a.ROWID
                WHERE maj.message_id IN ({placeholders})
                  AND a.filename IS NOT NULL
                """,
                rowids,
            )
            result: dict[int, list[str]] = {}
            home = str(Path.home())
            for msg_id, filename in cur.fetchall():
                path = Path(filename.replace("~", home, 1))
                if path.is_file():
                    result.setdefault(msg_id, []).append(str(path))
            conn.close()
            return result
        except Exception:
            return {}
