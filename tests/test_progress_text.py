import asyncio

from bao.channels.progress_text import (
    EditingProgress,
    IterationBuffer,
    ProgressBuffer,
    final_remainder,
    is_minor_tail,
    sanitize_progress_chunk,
)


def test_sanitize_progress_chunk_trims_leading_and_collapses_blank_lines() -> None:
    text = "\n\nhello\n\n\nworld"
    assert sanitize_progress_chunk(text) == "hello\n\nworld"


def test_final_remainder_with_large_overlap() -> None:
    streamed = "hello world"
    final = "hello world and"
    assert final_remainder(final, streamed) == " and"


def test_final_remainder_without_overlap_returns_full_text() -> None:
    streamed = "abc"
    final = "totally different"
    assert final_remainder(final, streamed) == final


def test_is_minor_tail_for_punctuation_only() -> None:
    assert is_minor_tail("。") is True
    assert is_minor_tail("!?") is True
    assert is_minor_tail("done") is False


def test_empty_tool_hint_still_flushes_iteration_boundary() -> None:
    buf = IterationBuffer()
    assert buf.process("chat", "先查一下", is_progress=True, is_tool_hint=False) == []
    assert buf.process("chat", "", is_progress=True, is_tool_hint=True) == ["先查一下"]


def test_progress_buffer_final_only_sends_tail_after_flushed_progress() -> None:
    sent: list[tuple[str, str]] = []

    async def _send(chat_id: str, text: str) -> None:
        sent.append((chat_id, text))

    buf = ProgressBuffer(_send, min_chars=8)

    async def _run() -> None:
        await buf.handle(
            "chat",
            "这是一个足够长的进度句子，会先发出去。",
            is_progress=True,
            is_tool_hint=False,
        )
        await buf.flush("chat", force=False)
        await buf.handle(
            "chat",
            "这是一个足够长的进度句子，会先发出去。然后再补一句结论。",
            is_progress=False,
            is_tool_hint=False,
        )

    asyncio.run(_run())

    assert sent == [
        ("chat", "这是一个足够长的进度句子，会先发出去。"),
        ("chat", "然后再补一句结论。"),
    ]


def test_progress_buffer_final_includes_unsent_pending_prefix_once() -> None:
    sent: list[tuple[str, str]] = []

    async def _send(chat_id: str, text: str) -> None:
        sent.append((chat_id, text))

    buf = ProgressBuffer(_send)

    async def _run() -> None:
        await buf.handle("chat", "你", is_progress=True, is_tool_hint=False)
        await buf.handle("chat", "好", is_progress=True, is_tool_hint=False)
        await buf.handle("chat", "你好", is_progress=False, is_tool_hint=False)

    asyncio.run(_run())

    assert sent == [("chat", "你好")]


def test_progress_buffer_tool_hint_seals_previous_turn() -> None:
    sent: list[tuple[str, str]] = []

    async def _send(chat_id: str, text: str) -> None:
        sent.append((chat_id, text))

    buf = ProgressBuffer(_send, min_chars=8)

    async def _run() -> None:
        await buf.handle(
            "chat",
            "这是一个足够长的进度句子，会先发出去。",
            is_progress=True,
            is_tool_hint=False,
        )
        await buf.handle(
            "chat",
            "🔎 Search Web: latest ai news",
            is_progress=True,
            is_tool_hint=True,
        )
        await buf.handle(
            "chat",
            "整理好了，这是最终答案。",
            is_progress=False,
            is_tool_hint=False,
        )

    asyncio.run(_run())

    assert sent == [
        ("chat", "这是一个足够长的进度句子，会先发出去。"),
        ("chat", "🔎 Search Web: latest ai news"),
        ("chat", "整理好了，这是最终答案。"),
    ]


def test_editing_progress_tool_hint_is_not_overwritten_by_final() -> None:
    created: list[str] = []
    updated: list[tuple[int, str]] = []

    async def _create(_chat_id: str, text: str) -> int:
        created.append(text)
        return len(created)

    async def _update(_chat_id: str, handle: int, text: str) -> int:
        updated.append((handle, text))
        return handle

    async def _send(_chat_id: str, text: str) -> None:
        raise AssertionError(f"unexpected plain send: {text}")

    handler = EditingProgress(_create, _update, _send, min_chars=8)

    async def _run() -> None:
        await handler.handle("chat", "我现在去看看。", is_progress=True, is_tool_hint=False)
        await handler.flush("chat", force=True)
        await handler.handle(
            "chat", "🤖 Delegate Task: run subagent", is_progress=True, is_tool_hint=True
        )
        await handler.handle("chat", "第二个也起好了。", is_progress=False, is_tool_hint=False)

    asyncio.run(_run())

    assert created == ["我现在去看看。", "🤖 Delegate Task: run subagent", "第二个也起好了。"]
    assert updated == []


def test_progress_buffer_tail_keeps_space_boundary_without_duplicate_prefix() -> None:
    sent: list[tuple[str, str]] = []

    async def _send(chat_id: str, text: str) -> None:
        sent.append((chat_id, text))

    buf = ProgressBuffer(_send, min_chars=5, hard_chars=6)

    async def _run() -> None:
        await buf.handle("chat", "Hello ", is_progress=True, is_tool_hint=False)
        await buf.flush("chat", force=False)
        await buf.handle("chat", "Hello world", is_progress=False, is_tool_hint=False)

    asyncio.run(_run())

    assert sent == [("chat", "Hello"), ("chat", "world")]
