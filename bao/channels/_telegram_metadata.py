"""Telegram ACL, thread, and metadata helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class _TelegramBotIdentity:
    user_id: int | None
    username: str | None


class _TelegramMetadataMixin:
    def is_allowed(self, sender_id: str) -> bool:
        if super().is_allowed(sender_id):
            return True

        allow_list = getattr(self.config, "allow_from", [])
        if not allow_list:
            return False

        sender_str = str(sender_id)
        if sender_str.count("|") != 1:
            return False

        sid, username = sender_str.split("|", 1)
        if not sid.isdigit() or not username:
            return False
        return sid in allow_list or username in allow_list

    @staticmethod
    def _sender_id(user: Any) -> str:
        sid = str(user.id)
        return f"{sid}|{user.username}" if user.username else sid

    @staticmethod
    def _coerce_int(value: object) -> int | None:
        if isinstance(value, int) and not isinstance(value, bool):
            return value
        if isinstance(value, str):
            raw = value.strip()
            if raw.lstrip("-").isdigit():
                return int(raw)
        return None

    @staticmethod
    def _derive_topic_session_key(message: Any) -> str | None:
        message_thread_id = getattr(message, "message_thread_id", None)
        if message.chat.type == "private" or message_thread_id is None:
            return None
        return f"telegram:{message.chat_id}:topic:{message_thread_id}"

    @staticmethod
    def _extract_reply_context(message: Any) -> str | None:
        reply = getattr(message, "reply_to_message", None)
        if not reply:
            return None
        text = getattr(reply, "text", None) or getattr(reply, "caption", None) or ""
        return f"[Reply to: {text}]" if text else None

    def _build_message_metadata(self, message: Any, user: Any) -> dict[str, Any]:
        reply_to = getattr(message, "reply_to_message", None)
        metadata: dict[str, Any] = {
            "message_id": message.message_id,
            "user_id": user.id,
            "username": user.username,
            "first_name": user.first_name,
            "is_group": message.chat.type != "private",
            "message_thread_id": getattr(message, "message_thread_id", None),
            "is_forum": bool(getattr(message.chat, "is_forum", False)),
            "reply_to_message_id": getattr(reply_to, "message_id", None) if reply_to else None,
        }
        session_key = self._derive_topic_session_key(message)
        if session_key is not None:
            metadata["session_key"] = session_key
        return metadata

    async def _ensure_bot_identity(self) -> _TelegramBotIdentity:
        if self._bot_user_id is not None or self._bot_username is not None:
            return _TelegramBotIdentity(self._bot_user_id, self._bot_username)
        if not self._app:
            return _TelegramBotIdentity(None, None)
        bot_info = await self._app.bot.get_me()
        self._bot_user_id = getattr(bot_info, "id", None)
        self._bot_username = getattr(bot_info, "username", None)
        return _TelegramBotIdentity(self._bot_user_id, self._bot_username)

    @staticmethod
    def _has_mention_entity(
        text: str,
        entities: Any,
        identity: _TelegramBotIdentity,
    ) -> bool:
        if not identity.username:
            return False
        handle = f"@{identity.username}".lower()
        bot_id = identity.user_id
        for entity in entities or []:
            entity_type = getattr(entity, "type", None)
            if entity_type == "text_mention":
                user = getattr(entity, "user", None)
                if user is not None and bot_id is not None and getattr(user, "id", None) == bot_id:
                    return True
                continue
            if entity_type != "mention":
                continue
            offset = getattr(entity, "offset", None)
            length = getattr(entity, "length", None)
            if offset is None or length is None:
                continue
            if text[offset : offset + length].lower() == handle:
                return True
        return handle in text.lower()

    async def _is_group_message_for_bot(self, message: Any) -> bool:
        if message.chat.type == "private" or self.config.group_policy == "open":
            return True

        identity = await self._ensure_bot_identity()
        if identity.username:
            text = message.text or ""
            caption = message.caption or ""
            if self._has_mention_entity(text, getattr(message, "entities", None), identity):
                return True
            if self._has_mention_entity(caption, getattr(message, "caption_entities", None), identity):
                return True

        reply_user = getattr(getattr(message, "reply_to_message", None), "from_user", None)
        bot_id = identity.user_id
        return bool(bot_id and reply_user and reply_user.id == bot_id)

    def _remember_thread_context(self, message: Any) -> None:
        message_thread_id = self._coerce_int(getattr(message, "message_thread_id", None))
        message_id = self._coerce_int(getattr(message, "message_id", None))
        if message_thread_id is None or message_id is None:
            return
        self._message_threads[(str(message.chat_id), message_id)] = message_thread_id
        if len(self._message_threads) > 1000:
            self._message_threads.pop(next(iter(self._message_threads)))
