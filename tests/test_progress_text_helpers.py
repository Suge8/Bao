from __future__ import annotations

from bao.channels.progress_text import (
    IterationBuffer,
    final_remainder,
    is_minor_tail,
    merge_progress_chunk,
    sanitize_progress_chunk,
)
from tests._progress_text_testkit import event


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


def test_merge_progress_chunk_accepts_cumulative_snapshot() -> None:
    assert merge_progress_chunk("你好", "你好世界") == "你好世界"


def test_merge_progress_chunk_keeps_monotonic_text_for_rewrite_snapshot() -> None:
    assert merge_progress_chunk("先给你起一个最小子代理", "先给你起一个最小测试代理") == "先给你起一个最小子代理"


def test_merge_progress_chunk_appends_delta_chunk() -> None:
    assert merge_progress_chunk("你好", "世界") == "你好世界"


def test_is_minor_tail_for_punctuation_only() -> None:
    assert is_minor_tail("。") is True
    assert is_minor_tail("!?") is True
    assert is_minor_tail("done") is False


def test_empty_tool_hint_still_flushes_iteration_boundary() -> None:
    buf = IterationBuffer()
    assert buf.process("chat", "先查一下", event(is_progress=True)) == []
    assert buf.process("chat", "", event(is_progress=True, is_tool_hint=True)) == ["先查一下"]
