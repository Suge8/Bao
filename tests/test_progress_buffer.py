from __future__ import annotations

import asyncio

from bao.channels.progress_text import ProgressBuffer, ProgressPolicy
from tests._progress_text_testkit import event


def test_progress_buffer_final_only_sends_tail_after_flushed_progress() -> None:
    sent: list[tuple[str, str]] = []

    async def send(chat_id: str, text: str) -> None:
        sent.append((chat_id, text))

    buf = ProgressBuffer(send, ProgressPolicy(min_chars=8))

    async def run() -> None:
        await buf.handle(
            "chat",
            "这是一个足够长的进度句子，会先发出去。",
            event(is_progress=True),
        )
        await buf.flush("chat", force=False)
        await buf.handle(
            "chat",
            "这是一个足够长的进度句子，会先发出去。然后再补一句结论。",
            event(is_progress=False),
        )

    asyncio.run(run())

    assert sent == [
        ("chat", "这是一个足够长的进度句子，会先发出去。"),
        ("chat", "然后再补一句结论。"),
    ]


def test_progress_buffer_final_includes_unsent_pending_prefix_once() -> None:
    sent: list[tuple[str, str]] = []

    async def send(chat_id: str, text: str) -> None:
        sent.append((chat_id, text))

    buf = ProgressBuffer(send)

    async def run() -> None:
        await buf.handle("chat", "你", event(is_progress=True))
        await buf.handle("chat", "好", event(is_progress=True))
        await buf.handle("chat", "你好", event(is_progress=False))

    asyncio.run(run())

    assert sent == [("chat", "你好")]


def test_progress_buffer_tool_hint_seals_previous_turn() -> None:
    sent: list[tuple[str, str]] = []

    async def send(chat_id: str, text: str) -> None:
        sent.append((chat_id, text))

    buf = ProgressBuffer(send, ProgressPolicy(min_chars=8))

    async def run() -> None:
        await buf.handle(
            "chat",
            "这是一个足够长的进度句子，会先发出去。",
            event(is_progress=True),
        )
        await buf.handle(
            "chat",
            "🔎 Search Web: latest ai news",
            event(is_progress=True, is_tool_hint=True),
        )
        await buf.handle(
            "chat",
            "整理好了，这是最终答案。",
            event(is_progress=False),
        )

    asyncio.run(run())

    assert sent == [
        ("chat", "这是一个足够长的进度句子，会先发出去。"),
        ("chat", "🔎 Search Web: latest ai news"),
        ("chat", "整理好了，这是最终答案。"),
    ]


def test_progress_buffer_tool_hint_flushes_main_scope_without_attribute_error() -> None:
    sent: list[tuple[str, str]] = []

    async def send(chat_id: str, text: str) -> None:
        sent.append((chat_id, text))

    buf = ProgressBuffer(send, ProgressPolicy(min_chars=1))

    async def run() -> None:
        await buf.handle("chat", "主进度", event(is_progress=True, scope="main:turn-1"))
        await buf.handle(
            "chat",
            "📨 发到会话",
            event(is_progress=True, is_tool_hint=True, scope="tool:turn-1"),
        )

    asyncio.run(run())

    assert sent == [("chat", "主进度"), ("chat", "📨 发到会话")]


def test_progress_buffer_tail_keeps_space_boundary_without_duplicate_prefix() -> None:
    sent: list[tuple[str, str]] = []

    async def send(chat_id: str, text: str) -> None:
        sent.append((chat_id, text))

    buf = ProgressBuffer(send, ProgressPolicy(min_chars=5, hard_chars=6))

    async def run() -> None:
        await buf.handle("chat", "Hello ", event(is_progress=True))
        await buf.flush("chat", force=False)
        await buf.handle("chat", "Hello world", event(is_progress=False))

    asyncio.run(run())

    assert sent == [("chat", "Hello"), ("chat", "world")]


def test_progress_buffer_accepts_snapshot_style_progress_without_duplicate_prefix() -> None:
    sent: list[tuple[str, str]] = []

    async def send(chat_id: str, text: str) -> None:
        sent.append((chat_id, text))

    buf = ProgressBuffer(send, ProgressPolicy(min_chars=1))

    async def run() -> None:
        await buf.handle("chat", "先给你起一个最小子代理", event(is_progress=True))
        await buf.flush("chat", force=True)
        await buf.handle("chat", "先给你起一个最小子代理测试", event(is_progress=True))
        await buf.flush("chat", force=True)

    asyncio.run(run())

    assert sent == [
        ("chat", "先给你起一个最小子代理"),
        ("chat", "测试"),
    ]
