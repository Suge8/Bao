"""Telegram channel outbound helpers."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from loguru import logger
from telegram import ReplyParameters
from telegram.error import BadRequest

from bao.bus.events import OutboundMessage

from ._telegram_common import (
    _is_message_not_modified,
    _is_telegram_parse_error,
    _markdown_to_telegram_html,
    _split_message,
)


@dataclass(frozen=True)
class _TelegramReplyContext:
    reply_params: ReplyParameters | None
    thread_kwargs: dict[str, int]


class _TelegramOutboundMixin:
    def _build_reply_context(
        self,
        msg: OutboundMessage,
    ) -> _TelegramReplyContext:
        meta = msg.metadata or {}
        reply_to_message_id = self._coerce_int(msg.reply_to or meta.get("message_id"))
        message_thread_id = self._coerce_int(meta.get("message_thread_id"))
        if message_thread_id is None and reply_to_message_id is not None:
            message_thread_id = self._message_threads.get((msg.chat_id, reply_to_message_id))
        thread_kwargs = (
            {"message_thread_id": message_thread_id} if message_thread_id is not None else {}
        )
        if not self.config.reply_to_message or reply_to_message_id is None:
            return _TelegramReplyContext(None, thread_kwargs)
        return _TelegramReplyContext(
            ReplyParameters(
                message_id=reply_to_message_id,
                allow_sending_without_reply=True,
            ),
            thread_kwargs,
        )

    async def _send_media_file(self, chat_id: int, media_path: str, context: _TelegramReplyContext) -> None:
        media_type = self._get_media_type(media_path)
        sender = {
            "photo": self._app.bot.send_photo,
            "voice": self._app.bot.send_voice,
            "audio": self._app.bot.send_audio,
        }.get(media_type, self._app.bot.send_document)
        param = "photo" if media_type == "photo" else media_type if media_type in ("voice", "audio") else "document"
        with open(media_path, "rb") as file_obj:
            await sender(
                chat_id=chat_id,
                **{param: file_obj},
                reply_parameters=context.reply_params,
                **context.thread_kwargs,
            )

    @staticmethod
    def _get_media_type(path: str) -> str:
        ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
        if ext in ("jpg", "jpeg", "png", "gif", "webp"):
            return "photo"
        if ext == "ogg":
            return "voice"
        if ext in ("mp3", "m4a", "wav", "aac"):
            return "audio"
        return "document"

    async def send(self, msg: OutboundMessage) -> None:
        if not self._app:
            logger.warning("⚠️ 未运行 / not running: Telegram bot")
            return

        meta = msg.metadata or {}
        if not bool(meta.get("_progress")):
            self._stop_typing(msg.chat_id)

        chat_id = self._require_chat_id(msg.chat_id)

        context = self._build_reply_context(msg)

        for media_path in msg.media or []:
            try:
                await self._send_media_file(chat_id, media_path, context)
            except Exception as exc:
                filename = media_path.rsplit("/", 1)[-1]
                logger.error("❌ 发送失败 / media failed: {}: {}", media_path, exc)
                await self._app.bot.send_message(
                    chat_id=chat_id,
                    text=f"[Failed to send: {filename}]",
                    reply_parameters=context.reply_params,
                    **context.thread_kwargs,
                )

        self._progress_reply_params[msg.chat_id] = context.reply_params
        self._progress_thread_kwargs[msg.chat_id] = dict(context.thread_kwargs)
        await self._dispatch_progress_text(msg, flush_progress=True)
        if bool(meta.get("_progress_clear")) or not meta.get("_progress"):
            self._progress_reply_params.pop(msg.chat_id, None)
            self._progress_thread_kwargs.pop(msg.chat_id, None)

    async def _send_text(self, chat_id: str, text: str) -> None:
        if not self._app or not text:
            return

        chat_id_int = self._require_chat_id(chat_id)

        context = _TelegramReplyContext(
            self._progress_reply_params.get(chat_id),
            self._progress_thread_kwargs.get(chat_id, {}),
        )
        for chunk in _split_message(text):
            await self._send_text_message(chat_id_int, chunk, context)

    async def _create_progress_text(self, chat_id: str, text: str) -> int | None:
        if not self._app or not text:
            return None

        chat_id_int = self._require_chat_id(chat_id)

        context = _TelegramReplyContext(
            self._progress_reply_params.get(chat_id),
            self._progress_thread_kwargs.get(chat_id, {}),
        )
        message = await self._send_text_message(chat_id_int, text, context)
        return int(message.message_id)

    async def _update_progress_text(
        self,
        chat_id: str,
        handle: int | None,
        text: str,
    ) -> int | None:
        if not self._app or handle is None or not text:
            return handle

        chat_id_int = self._require_chat_id(chat_id)

        html = _markdown_to_telegram_html(text)
        try:
            await self._app.bot.edit_message_text(
                chat_id=chat_id_int,
                message_id=handle,
                text=html,
                parse_mode="HTML",
            )
        except BadRequest as exc:
            if _is_message_not_modified(exc):
                return handle
            if not _is_telegram_parse_error(exc):
                raise
            logger.warning("⚠️ HTML 更新失败 / html edit failed: {}", exc)
            await self._app.bot.edit_message_text(
                chat_id=chat_id_int,
                message_id=handle,
                text=text,
            )
        return handle

    @staticmethod
    def _require_chat_id(chat_id: str) -> int:
        try:
            return int(chat_id)
        except ValueError as exc:
            logger.error("❌ 参数无效 / invalid chat_id: {}", chat_id)
            raise ValueError(f"invalid chat_id: {chat_id}") from exc

    async def _send_text_message(
        self,
        chat_id: int,
        text: str,
        context: _TelegramReplyContext,
    ) -> Any:
        assert self._app is not None
        html = _markdown_to_telegram_html(text)
        try:
            return await self._app.bot.send_message(
                chat_id=chat_id,
                text=html,
                parse_mode="HTML",
                reply_parameters=context.reply_params,
                **context.thread_kwargs,
            )
        except BadRequest as exc:
            if not _is_telegram_parse_error(exc):
                raise
            logger.warning("⚠️ HTML 发送失败 / html send failed: {}", exc)
            return await self._app.bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_parameters=context.reply_params,
                **context.thread_kwargs,
            )

    def _start_typing(self, chat_id: str) -> None:
        self._stop_typing(chat_id)
        self._typing_tasks[chat_id] = asyncio.create_task(self._typing_loop(chat_id))

    def _stop_typing(self, chat_id: str) -> None:
        task = self._typing_tasks.pop(chat_id, None)
        if task and not task.done():
            task.cancel()

    async def _typing_loop(self, chat_id: str) -> None:
        try:
            while self._app:
                await self._app.bot.send_chat_action(chat_id=int(chat_id), action="typing")
                await asyncio.sleep(4)
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.debug("Typing indicator stopped for {}: {}", chat_id, exc)

    def _get_extension(
        self,
        media_type: str,
        mime_type: str | None,
        filename: str | None = None,
    ) -> str:
        if mime_type:
            ext_map = {
                "image/jpeg": ".jpg",
                "image/png": ".png",
                "image/gif": ".gif",
                "audio/ogg": ".ogg",
                "audio/mpeg": ".mp3",
                "audio/mp4": ".m4a",
            }
            if mime_type in ext_map:
                return ext_map[mime_type]

        type_map = {"image": ".jpg", "voice": ".ogg", "audio": ".mp3"}
        if media_type in type_map:
            return type_map[media_type]

        if filename:
            return "".join(Path(filename).suffixes)
        return ""
