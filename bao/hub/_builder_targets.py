from __future__ import annotations

from dataclasses import dataclass
from typing import Any

CHANNEL_CONFIG_NAMES = (
    "telegram",
    "feishu",
    "dingtalk",
    "imessage",
    "qq",
    "email",
)
TELEGRAM_CHANNEL = "telegram"
WHATSAPP_CHANNEL = "whatsapp"
WHATSAPP_SUFFIX = "@s.whatsapp.net"


@dataclass
class _TargetAccumulator:
    logger: Any
    targets: list[tuple[str, str]]
    seen_targets: set[tuple[str, str]]

    def add(self, channel_name: str, chat_id: str) -> None:
        if not chat_id:
            self.logger.warning("⚠️ 目标跳过 / target skipped: {} empty chat_id", channel_name)
            return
        pair = (channel_name, chat_id)
        if pair in self.seen_targets:
            return
        self.seen_targets.add(pair)
        self.targets.append(pair)


def _extract_primary_id(raw_uid: Any) -> str:
    return str(raw_uid or "").split("|", 1)[0].strip()


def _is_telegram_chat_id(chat_id: str) -> bool:
    return bool(chat_id) and chat_id.lstrip("-").isdigit()


def _extract_telegram_target_id(raw_uid: Any) -> str:
    raw = str(raw_uid or "").strip()
    if not raw:
        return ""
    for part in raw.split("|"):
        token = part.strip()
        if _is_telegram_chat_id(token):
            return token
    return ""


def _resolve_allow_from_target(channel_name: str, raw_uid: Any) -> str:
    if channel_name == TELEGRAM_CHANNEL:
        return _extract_telegram_target_id(raw_uid)
    target = _extract_primary_id(raw_uid)
    if channel_name == WHATSAPP_CHANNEL and target and "@" not in target:
        return f"{target}{WHATSAPP_SUFFIX}"
    return target


def _iter_enabled_channel_configs(config: Any) -> list[tuple[str, Any]]:
    return [(name, getattr(config.channels, name)) for name in CHANNEL_CONFIG_NAMES]


def _collect_channel_targets(config: Any, logger: Any) -> list[tuple[str, str]]:
    targets: list[tuple[str, str]] = []
    seen_targets: set[tuple[str, str]] = set()
    accumulator = _TargetAccumulator(logger=logger, targets=targets, seen_targets=seen_targets)
    for name, cfg in _iter_enabled_channel_configs(config):
        if not (cfg.enabled and cfg.allow_from):
            continue
        for uid in cfg.allow_from:
            target = _resolve_allow_from_target(name, uid)
            if name == TELEGRAM_CHANNEL and not target:
                logger.warning(
                    "⚠️ 目标跳过 / target skipped: telegram requires numeric chat_id in allow_from ({})",
                    uid,
                )
                continue
            accumulator.add(name, target)

    whatsapp = config.channels.whatsapp
    if whatsapp.enabled and whatsapp.allow_from:
        for uid in whatsapp.allow_from:
            target = _resolve_allow_from_target(WHATSAPP_CHANNEL, uid)
            accumulator.add(WHATSAPP_CHANNEL, target)
    return targets


@dataclass(frozen=True)
class PrimaryTargetResolver:
    config: Any
    logger: Any

    def pick(self) -> tuple[str, str] | None:
        targets = _collect_channel_targets(self.config, self.logger)
        return targets[0] if targets else None
