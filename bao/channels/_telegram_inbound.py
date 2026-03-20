"""Telegram channel inbound helpers."""

from __future__ import annotations

import asyncio
from typing import Any

from loguru import logger
from telegram import Update
from telegram.ext import ContextTypes

from bao.bus.events import InboundMessage


class _TelegramInboundMixin:
    @staticmethod
    def _select_media_candidate(message: Any) -> tuple[Any, str | None]:
        if getattr(message, "photo", None):
            return message.photo[-1], "image"
        if getattr(message, "voice", None):
            return message.voice, "voice"
        if getattr(message, "audio", None):
            return message.audio, "audio"
        if getattr(message, "document", None):
            return message.document, "file"
        if getattr(message, "video", None):
            return message.video, "video"
        if getattr(message, "video_note", None):
            return message.video_note, "video"
        if getattr(message, "animation", None):
            return message.animation, "animation"
        return None, None

    async def _on_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        del context
        if not update.message or not update.effective_user:
            return

        user = update.effective_user
        await update.message.reply_text(
            f"👋 Hi {user.first_name}! I'm Bao.\n\n"
            "Send me a message and I'll respond!\n"
            "Type /help to see available commands."
        )

    async def _download_message_media(
        self,
        message: Any,
        *,
        add_failure_content: bool = False,
    ) -> tuple[list[str], list[str]]:
        from . import telegram as telegram_module

        media_file, media_type = self._select_media_candidate(message)
        if media_file is None or not self._app:
            return [], []

        try:
            file = await self._app.bot.get_file(media_file.file_id)
            media_kind = media_type or "file"
            ext = self._get_extension(
                media_kind,
                getattr(media_file, "mime_type", None),
                getattr(media_file, "file_name", None),
            )
            media_dir = telegram_module.get_media_dir("telegram")
            file_path = media_dir / f"{media_file.file_id[:16]}{ext}"
            await file.download_to_drive(str(file_path))

            path_str = str(file_path)
            if media_type in ("voice", "audio"):
                from bao.providers.transcription import GroqTranscriptionProvider

                transcriber = GroqTranscriptionProvider(api_key=self.groq_api_key)
                transcription = await transcriber.transcribe(file_path)
                if transcription:
                    logger.info("🎙️ 转写完成 / transcribed: {}: {}...", media_type, transcription[:50])
                    return [path_str], [f"[transcription: {transcription}]"]
            return [path_str], [f"[{media_kind}: {path_str}]"]
        except Exception as exc:
            logger.error("❌ 下载失败 / download failed: {}", exc)
            if add_failure_content and media_type is not None:
                return [], [f"[{media_type}: download failed]"]
            return [], []

    async def _forward_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        del context
        if not update.message or not update.effective_user:
            return
        message = update.message
        user = update.effective_user
        self._remember_thread_context(message)
        await self._handle_message(
            InboundMessage(
                channel=self.name,
                sender_id=self._sender_id(user),
                chat_id=str(message.chat_id),
                content=message.text or "",
                metadata=self._build_message_metadata(message, user),
            )
        )

    async def _on_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        del context
        if not update.message or not update.effective_user:
            return

        message = update.message
        user = update.effective_user
        chat_id = message.chat_id
        sender_id = self._sender_id(user)
        self._remember_thread_context(message)

        if not self.is_allowed(sender_id):
            logger.warning("⚠️ 访问拒绝 / access denied: sender={} channel=telegram", sender_id)
            return

        self._chat_ids[sender_id] = chat_id
        if not await self._is_group_message_for_bot(message):
            return

        content, media_paths = await self._build_inbound_payload(message)
        logger.debug("Telegram message from {}: {}...", sender_id, content[:50])

        str_chat_id = str(chat_id)
        metadata = self._build_message_metadata(message, user)

        media_group_id = getattr(message, "media_group_id", None)
        if media_group_id:
            group_item = {
                "sender_id": sender_id,
                "chat_id": str_chat_id,
                "content": content,
                "media": media_paths,
                "metadata": metadata,
            }
            key = self._buffer_media_group_item(
                chat_id=str_chat_id,
                media_group_id=str(media_group_id),
                item=group_item,
            )
            self._ensure_media_group_flush_task(key)
            return
        self._start_typing(str_chat_id)
        await self._handle_message(
            InboundMessage(
                channel=self.name,
                sender_id=sender_id,
                chat_id=str_chat_id,
                content=content,
                media=media_paths,
                metadata=metadata,
            )
        )

    async def _build_inbound_payload(self, message: Any) -> tuple[str, list[str]]:
        content_parts = self._initial_message_parts(message)
        media_paths, media_parts = await self._download_message_media(message, add_failure_content=True)
        content_parts.extend(media_parts)
        media_paths = await self._prepend_reply_media_and_context(message, content_parts, media_paths)
        content = "\n".join(content_parts) if content_parts else "[empty message]"
        return content, media_paths

    @staticmethod
    def _initial_message_parts(message: Any) -> list[str]:
        parts: list[str] = []
        if message.text:
            parts.append(message.text)
        if message.caption:
            parts.append(message.caption)
        return parts

    async def _prepend_reply_media_and_context(
        self,
        message: Any,
        content_parts: list[str],
        media_paths: list[str],
    ) -> list[str]:
        reply = getattr(message, "reply_to_message", None)
        if reply is None:
            return media_paths
        reply_context = self._extract_reply_context(message)
        reply_media_paths, reply_media_parts = await self._download_message_media(reply)
        reply_tag = reply_context or self._fallback_reply_tag(reply_media_parts)
        if reply_tag:
            content_parts.insert(0, reply_tag)
        if not reply_media_paths:
            return media_paths
        return [*reply_media_paths, *media_paths]

    @staticmethod
    def _fallback_reply_tag(reply_media_parts: list[str]) -> str | None:
        if not reply_media_parts:
            return None
        return f"[Reply to: {reply_media_parts[0]}]"

    def _buffer_media_group_item(
        self,
        *,
        chat_id: str,
        media_group_id: str,
        item: dict[str, Any],
    ) -> str:
        key = f"{chat_id}:{media_group_id}"
        self._media_group_buffers.setdefault(key, []).append(item)
        return key

    def _ensure_media_group_flush_task(self, key: str) -> None:
        task = self._media_group_tasks.get(key)
        if task is None or task.done():
            self._media_group_tasks[key] = asyncio.create_task(self._flush_media_group(key))

    async def _flush_media_group(self, key: str) -> None:
        try:
            await asyncio.sleep(0.6)
            items = self._media_group_buffers.pop(key, [])
            if not items:
                return

            sender_id = str(items[-1]["sender_id"])
            chat_id = str(items[-1]["chat_id"])
            metadata_obj = items[-1].get("metadata", {})
            metadata = metadata_obj if isinstance(metadata_obj, dict) else {}

            contents = [str(item.get("content", "")).strip() for item in items]
            merged_content = "\n".join(content for content in contents if content and content != "[empty message]")
            if not merged_content:
                merged_content = "[empty message]"

            merged_media: list[str] = []
            for item in items:
                media_obj = item.get("media", [])
                if isinstance(media_obj, list):
                    for media_path in media_obj:
                        if isinstance(media_path, str):
                            merged_media.append(media_path)
            merged_media = list(dict.fromkeys(merged_media))

            await self._handle_message(
                InboundMessage(
                    channel=self.name,
                    sender_id=sender_id,
                    chat_id=chat_id,
                    content=merged_content,
                    media=merged_media,
                    metadata=metadata,
                )
            )
        except asyncio.CancelledError:
            self._media_group_buffers.pop(key, None)
            raise
        except Exception as exc:
            logger.error("❌ 媒体组处理失败 / media-group flush failed: {}", exc)
        finally:
            self._media_group_tasks.pop(key, None)
