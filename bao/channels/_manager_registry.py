from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from loguru import logger

from bao.bus.queue import MessageBus
from bao.channels.base import BaseChannel
from bao.config.schema import Config

UnavailableReporter = Callable[[str, Any], None]
ChannelFactory = Callable[[], BaseChannel]


@dataclass
class ChannelRegistryContext:
    config: Config
    bus: MessageBus
    channels: dict[str, BaseChannel]
    report_unavailable: UnavailableReporter


def init_channels(context: ChannelRegistryContext) -> None:
    registrar = _ChannelRegistrar(context)
    registrar.register_telegram()
    registrar.register_whatsapp()
    registrar.register_discord()
    registrar.register_feishu()
    registrar.register_mochat()
    registrar.register_dingtalk()
    registrar.register_email()
    registrar.register_slack()
    registrar.register_qq()
    registrar.register_imessage()


class _ChannelRegistrar:
    def __init__(self, context: ChannelRegistryContext) -> None:
        self._context = context

    def register_telegram(self) -> None:
        if not self._context.config.channels.telegram.enabled:
            return
        try:
            from bao.channels.telegram import TelegramChannel
        except ImportError as exc:
            self._report_unavailable("Telegram", exc)
            return
        groq_cfg = self._context.config.providers.get("groq")
        groq_api_key = groq_cfg.api_key.get_secret_value() if groq_cfg else ""
        self._register(
            "telegram",
            lambda: TelegramChannel(self._context.config.channels.telegram, self._context.bus, groq_api_key),
        )

    def register_whatsapp(self) -> None:
        if not self._context.config.channels.whatsapp.enabled:
            return
        try:
            from bao.channels.whatsapp import WhatsAppChannel
        except ImportError as exc:
            self._report_unavailable("WhatsApp", exc)
            return
        self._register(
            "whatsapp",
            lambda: WhatsAppChannel(self._context.config.channels.whatsapp, self._context.bus),
        )

    def register_discord(self) -> None:
        if not self._context.config.channels.discord.enabled:
            return
        try:
            from bao.channels.discord import DiscordChannel
        except ImportError as exc:
            self._report_unavailable("Discord", exc)
            return
        self._register(
            "discord",
            lambda: DiscordChannel(self._context.config.channels.discord, self._context.bus),
        )

    def register_feishu(self) -> None:
        if not self._context.config.channels.feishu.enabled:
            return
        try:
            from bao.channels.feishu import FEISHU_AVAILABLE, FeishuChannel
        except ImportError as exc:
            self._report_unavailable("Feishu", exc)
            return
        if not FEISHU_AVAILABLE:
            self._report_unavailable("Feishu", "sdk missing")
            return
        self._register(
            "feishu",
            lambda: FeishuChannel(self._context.config.channels.feishu, self._context.bus),
        )

    def register_mochat(self) -> None:
        if not self._context.config.channels.mochat.enabled:
            return
        try:
            from bao.channels.mochat import MochatChannel
        except ImportError as exc:
            self._report_unavailable("Mochat", exc)
            return
        self._register(
            "mochat",
            lambda: MochatChannel(self._context.config.channels.mochat, self._context.bus),
        )

    def register_dingtalk(self) -> None:
        if not self._context.config.channels.dingtalk.enabled:
            return
        try:
            from bao.channels.dingtalk import DINGTALK_AVAILABLE, DingTalkChannel
        except ImportError as exc:
            self._report_unavailable("DingTalk", exc)
            return
        if not DINGTALK_AVAILABLE:
            self._report_unavailable("DingTalk", "sdk missing")
            return
        self._register(
            "dingtalk",
            lambda: DingTalkChannel(self._context.config.channels.dingtalk, self._context.bus),
        )

    def register_email(self) -> None:
        if not self._context.config.channels.email.enabled:
            return
        try:
            from bao.channels.email import EmailChannel
        except ImportError as exc:
            self._report_unavailable("Email", exc)
            return
        self._register(
            "email",
            lambda: EmailChannel(self._context.config.channels.email, self._context.bus),
        )

    def register_slack(self) -> None:
        if not self._context.config.channels.slack.enabled:
            return
        try:
            from bao.channels.slack import SlackChannel
        except ImportError as exc:
            self._report_unavailable("Slack", exc)
            return
        self._register(
            "slack",
            lambda: SlackChannel(self._context.config.channels.slack, self._context.bus),
        )

    def register_qq(self) -> None:
        if not self._context.config.channels.qq.enabled:
            return
        try:
            from bao.channels.qq import QQ_AVAILABLE, QQChannel
        except ImportError as exc:
            self._report_unavailable("QQ", exc)
            return
        if not QQ_AVAILABLE:
            self._report_unavailable("QQ", "sdk missing")
            return
        self._register("qq", lambda: QQChannel(self._context.config.channels.qq, self._context.bus))

    def register_imessage(self) -> None:
        if not self._context.config.channels.imessage.enabled:
            return
        try:
            from bao.channels.imessage import IMessageChannel
        except ImportError as exc:
            self._report_unavailable("iMessage", exc)
            return
        self._register(
            "imessage",
            lambda: IMessageChannel(self._context.config.channels.imessage, self._context.bus),
        )

    def _register(self, key: str, factory: ChannelFactory) -> None:
        self._context.channels[key] = factory()
        logger.debug("{} channel enabled", key.capitalize())

    def _report_unavailable(self, name: str, detail: Any) -> None:
        self._context.report_unavailable(name, detail)
