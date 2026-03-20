from __future__ import annotations

from tests._consolidate_offset_testkit import (
    KEEP_COUNT,
    Session,
    create_session_with_messages,
    get_old_messages,
)


class TestSessionImmutableHistory:
    def test_initial_state(self) -> None:
        assert Session(key="test:initial").messages == []

    def test_add_messages_appends_only(self) -> None:
        session = Session(key="test:preserve")
        session.add_message("user", "msg1")
        session.add_message("assistant", "resp1")
        session.add_message("user", "msg2")
        assert len(session.messages) == 3
        assert session.messages[0]["content"] == "msg1"

    def test_get_history_returns_most_recent(self) -> None:
        session = Session(key="test:history")
        for index in range(10):
            session.add_message("user", f"msg{index}")
            session.add_message("assistant", f"resp{index}")

        history = session.get_history(max_messages=6)
        assert len(history) == 6
        assert history[0]["content"] == "msg7"
        assert history[-1]["content"] == "resp9"

    def test_get_history_with_all_messages(self) -> None:
        history = create_session_with_messages("test:all", 5).get_history(max_messages=100)
        assert len(history) == 5
        assert history[0]["content"] == "msg0"

    def test_get_display_history_keeps_assistant_only_tail(self) -> None:
        session = Session(key="test:display-tail")
        session.add_message("user", "u0")
        session.add_message("assistant", "a0")
        session.add_message("assistant", "a1")
        session.last_consolidated = 1

        assert session.get_history(max_messages=10) == []
        display = session.get_display_history(max_messages=10)
        assert [item["content"] for item in display] == ["a0", "a1"]

    def test_get_display_history_preserves_format_and_entrance_style(self) -> None:
        session = Session(key="test:display-meta")
        session.add_message("assistant", "**a0**", format="markdown")
        session.add_message("system", "welcome", entrance_style="greeting", format="plain")

        display = session.get_display_history(max_messages=10)
        assert display[0]["format"] == "markdown"
        assert display[1]["entrance_style"] == "greeting"

    def test_get_history_stable_for_same_session(self) -> None:
        session = create_session_with_messages("test:stable", 20)
        assert session.get_history(max_messages=10) == session.get_history(max_messages=10)

    def test_messages_list_never_modified(self) -> None:
        session = create_session_with_messages("test:immutable", 5)
        original_len = len(session.messages)
        session.get_history(max_messages=2)
        for _ in range(10):
            session.get_history(max_messages=3)
        assert len(session.messages) == original_len


class TestGetHistoryWithConsolidation:
    def test_get_history_respects_last_consolidated(self) -> None:
        session = Session(key="test:cursor")
        for index in range(10):
            session.add_message("user", f"old{index}")
            session.add_message("assistant", f"reply{index}")
        session.last_consolidated = 10
        session.add_message("user", "new0")
        session.add_message("assistant", "newreply0")

        contents = [message["content"] for message in session.get_history(max_messages=500)]
        assert "old0" not in contents
        assert "new0" in contents

    def test_get_history_aligns_to_user_turn(self) -> None:
        session = Session(key="test:align")
        session.messages = [
            {"role": "user", "content": "q0", "timestamp": ""},
            {"role": "assistant", "content": "", "timestamp": "", "tool_calls": [{"id": "c1"}]},
            {"role": "tool", "content": "result", "timestamp": "", "tool_call_id": "c1"},
            {"role": "user", "content": "q1", "timestamp": ""},
            {"role": "assistant", "content": "ans1", "timestamp": ""},
        ]
        session.last_consolidated = 1
        history = session.get_history(max_messages=500)
        assert history[0]["role"] == "user"
        assert history[0]["content"] == "q1"

    def test_get_history_no_user_returns_empty(self) -> None:
        session = Session(key="test:nouser")
        session.messages = [
            {"role": "assistant", "content": "x", "timestamp": ""},
            {"role": "tool", "content": "y", "timestamp": "", "tool_call_id": "c1"},
        ]
        assert session.get_history(max_messages=500) == []

    def test_get_history_last_consolidated_zero_unchanged(self) -> None:
        session = Session(key="test:zero")
        session.add_message("user", "hello")
        session.add_message("assistant", "hi")
        history = session.get_history(max_messages=500)
        assert len(history) == 2
        assert history[0]["role"] == "user"


class TestEmptyAndBoundarySessions:
    def test_empty_session_consolidation(self) -> None:
        session = Session(key="test:empty")
        assert session.last_consolidated == 0
        assert len(session.messages) - session.last_consolidated == 0
        assert get_old_messages(session, session.last_consolidated, KEEP_COUNT) == []

    def test_single_message_session(self) -> None:
        session = Session(key="test:single")
        session.add_message("user", "only message")
        assert get_old_messages(session, session.last_consolidated, KEEP_COUNT) == []

    def test_exactly_keep_count_messages(self) -> None:
        session = create_session_with_messages("test:exact", KEEP_COUNT)
        assert get_old_messages(session, session.last_consolidated, KEEP_COUNT) == []

    def test_just_over_keep_count(self) -> None:
        session = create_session_with_messages("test:over", KEEP_COUNT + 1)
        old_messages = get_old_messages(session, session.last_consolidated, KEEP_COUNT)
        assert len(old_messages) == 1
        assert old_messages[0]["content"] == "msg0"
