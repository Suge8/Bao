"""Email lifecycle helpers."""

from __future__ import annotations

import asyncio

from loguru import logger

from bao.bus.events import InboundMessage


class _EmailLifecycleMixin:
    async def start(self) -> None:
        self.mark_not_ready()
        if not self.config.consent_granted:
            logger.warning("⚠️ 邮件通道未授权 / consent missing: set channels.email.consentGranted=true")
            self.mark_ready()
            return
        if not self._validate_config():
            self.mark_ready()
            return

        self._start_lifecycle()
        self.mark_ready()
        logger.info("📡 邮件通道启动 / channel start: IMAP polling mode")

        poll_seconds = max(5, int(self.config.poll_interval_seconds))
        while self._running:
            try:
                inbound_items = await asyncio.to_thread(self._fetch_new_messages)
                for item in inbound_items:
                    self._remember_inbound_headers(item)
                    await self._handle_message(
                        InboundMessage(
                            channel=self.name,
                            sender_id=item["sender"],
                            chat_id=item["sender"],
                            content=item["content"],
                            metadata=item.get("metadata", {}),
                        )
                    )
            except Exception as exc:
                logger.error("❌ 邮件轮询异常 / polling error: {}", exc)

            if await self._wait_stop_or_timeout(poll_seconds):
                break

    def _remember_inbound_headers(self, item: dict[str, object]) -> None:
        sender = str(item["sender"])
        subject = str(item.get("subject", "") or "")
        message_id = str(item.get("message_id", "") or "")
        if subject:
            self._last_subject_by_chat[sender] = subject
        if message_id:
            self._last_message_id_by_chat[sender] = message_id

    async def stop(self) -> None:
        self._stop_lifecycle()
        self.mark_not_ready()
        self._reset_lifecycle()
