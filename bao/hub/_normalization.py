"""Hub 归一化工具函数"""
from __future__ import annotations


def normalize_text(value: object) -> str:
    """归一化文本值（用于 profile_id, session_key 等）"""
    if isinstance(value, bool):
        return ""
    if isinstance(value, int):
        return str(value)
    if not isinstance(value, str):
        return ""
    return value.strip()


def normalize_channel(value: object) -> str:
    """归一化 channel 名称（小写）"""
    return normalize_text(value).lower()


def normalize_media(media: list[str] | None) -> list[str] | None:
    """归一化媒体路径列表"""
    if media is None:
        return None
    normalized = [item.strip() for item in media if isinstance(item, str) and item.strip()]
    return normalized or None
