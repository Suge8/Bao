from bao.channels.progress_text import (
    IterationBuffer,
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
