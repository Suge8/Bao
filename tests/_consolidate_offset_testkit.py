"""Shared helpers for consolidation offset tests."""

from __future__ import annotations

from bao.agent.loop import _archive_all_signature
from bao.session.manager import Session, SessionManager

MEMORY_WINDOW = 50
KEEP_COUNT = MEMORY_WINDOW // 2


def create_session_with_messages(key: str, count: int, role: str = "user") -> Session:
    session = Session(key=key)
    for index in range(count):
        session.add_message(role, f"msg{index}")
    return session


def assert_messages_content(messages: list[dict[str, str]], start_index: int, end_index: int) -> None:
    assert messages
    assert messages[0]["content"] == f"msg{start_index}"
    assert messages[-1]["content"] == f"msg{end_index}"


def get_old_messages(session: Session, last_consolidated: int, keep_count: int) -> list[dict[str, str]]:
    return session.messages[last_consolidated:-keep_count]


__all__ = [
    "KEEP_COUNT",
    "MEMORY_WINDOW",
    "Session",
    "SessionManager",
    "_archive_all_signature",
    "assert_messages_content",
    "create_session_with_messages",
    "get_old_messages",
]
