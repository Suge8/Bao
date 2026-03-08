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
from bao.channels.progress_text import ProgressBuffer
from bao.config.schema import IMessageConfig

CHAT_DB = Path.home() / "Library" / "Messages" / "chat.db"
APPLE_EPOCH_OFFSET = 978307200


def permission_target_label(executable: str) -> str:
    return Path(executable).name or executable


def automation_permission_hint(error_text: str, executable: str) -> str | None:
    if "-1743" not in error_text:
        return None
    return (
        "grant Automation for {} -> Messages in System Settings > Privacy & Security > Automation"
    ).format(permission_target_label(executable))


class IMessageChannel(BaseChannel):
    name = "imessage"

    def __init__(self, config: IMessageConfig, bus: MessageBus):
        super().__init__(config, bus)
        self.config: IMessageConfig = config
        self._last_rowid: int = 0
        self._poll_interval: float = config.poll_interval
        self._progress_handler = ProgressBuffer(self._send_text)

    async def start(self) -> None:
        self.mark_not_ready()
        if not CHAT_DB.exists():
            logger.error("❌ iMessage 数据库缺失 / db missing: need Full Disk Access")
            self.mark_ready()
            return
        self._running = True
        self._last_rowid = self._get_max_rowid()
        self.mark_ready()
        if self._last_rowid == 0:
            logger.warning(
                "⚠️ iMessage 无法读库 / db unreadable: ROWID=0, grant Full Disk Access for {}",
                permission_target_label(sys.executable),
            )
        logger.debug("iMessage channel started (polling from ROWID {})", self._last_rowid)
        while self._running:
            try:
                await self._poll()
            except Exception as e:
                logger.error("❌ iMessage 轮询异常 / poll error: {}", e)
            await asyncio.sleep(self._poll_interval)

    async def stop(self) -> None:
        self._clear_progress()
        self._running = False
        self.mark_not_ready()

    async def send(self, msg: OutboundMessage) -> None:
        await self._dispatch_progress_text(msg, flush_progress=False)
        for file_path in msg.media or []:
            if Path(file_path).is_file():
                await self._send_file(msg.chat_id, file_path)
            else:
                logger.debug("ℹ️ iMessage 媒体缺失 / media missing: {}", file_path)

    def _service_type(self) -> str:
        service = (self.config.service or "iMessage").strip()
        return service if service in {"iMessage", "SMS"} else "iMessage"

    async def _send_text(self, buddy: str, text: str) -> None:
        encoded = text.replace("\\", "\\\\").replace('"', '\\"')
        service = self._service_type()
        script = (
            f'tell application "Messages"\n'
            f"  set targetService to 1st account whose service type = {service}\n"
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
                error_text = stderr.decode().strip()
                logger.error("❌ iMessage 文本发送失败 / send failed: {}", error_text)
                if hint := automation_permission_hint(error_text, sys.executable):
                    logger.warning("⚠️ iMessage 自动化未授权 / automation denied: {}", hint)
        except Exception as e:
            logger.error("❌ iMessage 文本发送异常 / send error: {}", e)

    async def _send_file(self, buddy: str, file_path: str) -> None:
        """Send a file (image/doc) via AppleScript POSIX file."""
        escaped = file_path.replace("\\", "\\\\").replace('"', '\\"')
        service = self._service_type()
        script = (
            f'tell application "Messages"\n'
            f"  set targetService to 1st account whose service type = {service}\n"
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
                error_text = stderr.decode().strip()
                logger.error("❌ iMessage 文件发送失败 / send failed: {}", error_text)
                if hint := automation_permission_hint(error_text, sys.executable):
                    logger.warning("⚠️ iMessage 自动化未授权 / automation denied: {}", hint)
        except Exception as e:
            logger.error("❌ iMessage 文件发送异常 / send error: {}", e)

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
            if media:
                logger.debug("iMessage media for ROWID {}: {}", rowid, media)
            content = text or ("[attachment]" if media else "")
            await self._handle_message(
                sender_id=sender,
                chat_id=chat_id,
                content=content,
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
                SELECT maj.message_id, a.filename, a.transfer_name, a.mime_type
                FROM message_attachment_join maj
                JOIN attachment a ON maj.attachment_id = a.ROWID
                WHERE maj.message_id IN ({placeholders})
                """,
                rowids,
            )
            result: dict[int, list[str]] = {}
            home = str(Path.home())
            raw_rows = cur.fetchall()
            if not raw_rows:
                logger.debug("iMessage: no attachment rows found for ROWIDs {}", rowids)
            for msg_id, filename, transfer_name, mime_type in raw_rows:
                logger.debug(
                    "iMessage attachment: ROWID={} filename={} transfer_name={} mime={}",
                    msg_id,
                    filename,
                    transfer_name,
                    mime_type,
                )
                actual_name = filename or transfer_name
                if not actual_name:
                    continue
                path = Path(actual_name.replace("~", home, 1))
                if path.is_file():
                    result.setdefault(msg_id, []).append(str(path))
                else:
                    logger.debug("iMessage attachment file not found: {}", path)
            conn.close()
            return result
        except Exception as e:
            logger.warning("⚠️ iMessage 附件查询失败 / attachment query failed: {}", e)
            return {}
