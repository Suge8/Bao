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

CHAT_DB = Path.home() / "Library" / "Messages" / "chat.db"
APPLE_EPOCH_OFFSET = 978307200


class IMessageChannel(BaseChannel):
    name = "imessage"

    def __init__(self, config: IMessageConfig, bus: MessageBus):
        super().__init__(config, bus)
        self.config: IMessageConfig = config
        self._last_rowid: int = 0
        self._poll_interval: float = config.poll_interval

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
        self._running = False

    async def send(self, msg: OutboundMessage) -> None:
        buddy = msg.chat_id
        text = (msg.content or "").replace("\\", "\\\\").replace('"', '\\"')
        script = (
            f'tell application "Messages"\n'
            f"  set targetService to 1st account whose service type = iMessage\n"
            f'  set targetBuddy to buddy "{buddy}" of targetService\n'
            f'  send "{text}" to targetBuddy\n'
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
        for rowid, text, sender, chat_id in rows:
            if not text:
                continue
            if not self.is_allowed(sender):
                continue
            self._last_rowid = max(self._last_rowid, rowid)
            await self._handle_message(
                sender_id=sender,
                chat_id=chat_id,
                content=text,
            )

    def _query_new(self) -> list[tuple]:
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
                    WHERE m.ROWID > ? AND m.is_from_me = 0 AND m.text IS NOT NULL
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
