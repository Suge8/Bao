from __future__ import annotations

import asyncio

from bao.channels.progress_text import EditingProgress, EditingProgressOps, ProgressPolicy
from tests._progress_text_testkit import event


def test_editing_progress_tool_hint_is_not_overwritten_by_final() -> None:
    created: list[str] = []
    updated: list[tuple[int, str]] = []

    async def create(_chat_id: str, text: str) -> int:
        created.append(text)
        return len(created)

    async def update(_chat_id: str, handle: int, text: str) -> int:
        updated.append((handle, text))
        return handle

    handler = EditingProgress(
        EditingProgressOps(create=create, update=update),
        ProgressPolicy(min_chars=8),
    )

    async def run() -> None:
        await handler.handle("chat", "我现在去看看。", event(is_progress=True))
        await handler.flush("chat", force=True)
        await handler.handle("chat", "🤖 Delegate Task: run subagent", event(is_progress=True, is_tool_hint=True))
        await handler.handle("chat", "第二个也起好了。", event(is_progress=False))

    asyncio.run(run())

    assert created == ["我现在去看看。", "🤖 Delegate Task: run subagent", "第二个也起好了。"]
    assert updated == []


def test_editing_progress_tool_hint_seals_main_scope_before_final_turn() -> None:
    created: list[str] = []
    updated: list[tuple[int, str]] = []

    async def create(_chat_id: str, text: str) -> int:
        created.append(text)
        return len(created)

    async def update(_chat_id: str, handle: int, text: str) -> int:
        updated.append((handle, text))
        return handle

    handler = EditingProgress(
        EditingProgressOps(create=create, update=update),
        ProgressPolicy(min_chars=1),
    )

    async def run() -> None:
        await handler.handle(
            "chat",
            "我现在去看看。",
            event(is_progress=True, scope="main:turn-1"),
        )
        await handler.flush("chat", force=True, scope="main:turn-1")
        await handler.handle(
            "chat",
            "🔎 Search Web: latest ai news",
            event(is_progress=True, is_tool_hint=True, scope="tool:turn-1"),
        )
        await handler.handle(
            "chat",
            "第二个也起好了。",
            event(is_progress=False, scope="main:turn-1"),
        )

    asyncio.run(run())

    assert created == [
        "我现在去看看。",
        "🔎 Search Web: latest ai news",
        "第二个也起好了。",
    ]
    assert updated == []


def test_editing_progress_progress_updates_stay_monotonic() -> None:
    created: list[str] = []
    updated: list[tuple[int, str]] = []

    async def create(_chat_id: str, text: str) -> int:
        created.append(text)
        return 1

    async def update(_chat_id: str, handle: int, text: str) -> int:
        updated.append((handle, text))
        return handle

    handler = EditingProgress(
        EditingProgressOps(create=create, update=update),
        ProgressPolicy(min_chars=1),
    )

    async def run() -> None:
        await handler.handle("chat", "你好世界", event(is_progress=True))
        await handler.flush("chat", force=True)
        await handler.handle("chat", "你好，重新组织一下", event(is_progress=True))
        await handler.flush("chat", force=True)

    asyncio.run(run())

    assert created == ["你好世界"]
    assert updated == []


def test_editing_progress_final_still_allows_rewrite() -> None:
    created: list[str] = []
    updated: list[tuple[int, str]] = []

    async def create(_chat_id: str, text: str) -> int:
        created.append(text)
        return 1

    async def update(_chat_id: str, handle: int, text: str) -> int:
        updated.append((handle, text))
        return handle

    handler = EditingProgress(
        EditingProgressOps(create=create, update=update),
        ProgressPolicy(min_chars=1),
    )

    async def run() -> None:
        await handler.handle("chat", "你好世界", event(is_progress=True))
        await handler.flush("chat", force=True)
        await handler.handle("chat", "你好，重新组织一下", event(is_progress=False))

    asyncio.run(run())

    assert created == ["你好世界"]
    assert updated == [(1, "你好，重新组织一下")]


def test_editing_progress_final_can_append_tail_without_rewrite() -> None:
    created: list[str] = []
    updated: list[tuple[int, str]] = []

    async def create(_chat_id: str, text: str) -> int:
        created.append(text)
        return len(created)

    async def update(_chat_id: str, handle: int, text: str) -> int:
        updated.append((handle, text))
        return handle

    handler = EditingProgress(
        EditingProgressOps(create=create, update=update),
        ProgressPolicy(min_chars=1),
        rewrite_final=False,
    )

    async def run() -> None:
        await handler.handle("chat", "这是已经显示出来的进度。", event(is_progress=True))
        await handler.flush("chat", force=True)
        await handler.handle("chat", "这是已经显示出来的进度。然后补一句结论。", event(is_progress=False))

    asyncio.run(run())

    assert created == ["这是已经显示出来的进度。", "然后补一句结论。"]
    assert updated == []
