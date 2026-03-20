"""Email outbound helpers."""

from __future__ import annotations

import asyncio
import ssl
from email.message import EmailMessage

from loguru import logger

from bao.bus.events import OutboundMessage


class _EmailOutboundMixin:
    async def send(self, msg: OutboundMessage) -> None:
        if not self.config.consent_granted:
            logger.warning("⚠️ 邮件发送已跳过 / send skipped: consent_granted is false")
            return
        if not self.config.smtp_host:
            logger.warning("⚠️ 邮件 SMTP 未配置 / smtp missing: host not configured")
            return

        to_addr = msg.chat_id.strip()
        if not to_addr:
            logger.warning("⚠️ 邮件收件人缺失 / recipient missing: empty address")
            return

        is_reply = to_addr in self._last_subject_by_chat
        force_send = bool((msg.metadata or {}).get("force_send"))
        if is_reply and not self.config.auto_reply_enabled and not force_send:
            logger.info("ℹ️ 自动回复已跳过 / reply skipped: {} auto_reply_enabled is false", to_addr)
            return

        email_msg = self._build_email_message(msg, to_addr)
        try:
            await asyncio.to_thread(self._smtp_send, email_msg)
        except Exception as exc:
            logger.error("❌ 邮件发送异常 / send error: {}: {}", to_addr, exc)
            raise

    def _build_email_message(self, msg: OutboundMessage, to_addr: str) -> EmailMessage:
        base_subject = self._last_subject_by_chat.get(to_addr, "Bao reply")
        subject = self._reply_subject(base_subject)
        if msg.metadata and isinstance(msg.metadata.get("subject"), str):
            override = msg.metadata["subject"].strip()
            if override:
                subject = override

        email_msg = EmailMessage()
        email_msg["From"] = (
            self.config.from_address or self.config.smtp_username or self.config.imap_username
        )
        email_msg["To"] = to_addr
        email_msg["Subject"] = subject
        email_msg.set_content(msg.content or "")

        in_reply_to = self._last_message_id_by_chat.get(to_addr)
        if in_reply_to:
            email_msg["In-Reply-To"] = in_reply_to
            email_msg["References"] = in_reply_to
        return email_msg

    def _validate_config(self) -> bool:
        missing = []
        imap_password = self.config.imap_password.get_secret_value()
        smtp_password = self.config.smtp_password.get_secret_value()
        if not self.config.imap_host:
            missing.append("imap_host")
        if not self.config.imap_username:
            missing.append("imap_username")
        if not imap_password:
            missing.append("imap_password")
        if not self.config.smtp_host:
            missing.append("smtp_host")
        if not self.config.smtp_username:
            missing.append("smtp_username")
        if not smtp_password:
            missing.append("smtp_password")
        if missing:
            logger.error("❌ 邮件配置缺失 / config missing: {}", ", ".join(missing))
            return False
        return True

    def _smtp_send(self, msg: EmailMessage) -> None:
        from . import email as email_module

        timeout = 30
        smtp_password = self.config.smtp_password.get_secret_value()
        if self.config.smtp_use_ssl:
            with email_module.smtplib.SMTP_SSL(
                self.config.smtp_host,
                self.config.smtp_port,
                timeout=timeout,
            ) as smtp:
                smtp.login(self.config.smtp_username, smtp_password)
                smtp.send_message(msg)
            return

        with email_module.smtplib.SMTP(
            self.config.smtp_host,
            self.config.smtp_port,
            timeout=timeout,
        ) as smtp:
            if self.config.smtp_use_tls:
                smtp.starttls(context=ssl.create_default_context())
            smtp.login(self.config.smtp_username, smtp_password)
            smtp.send_message(msg)
