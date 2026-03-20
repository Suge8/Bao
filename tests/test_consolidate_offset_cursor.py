from __future__ import annotations

from pathlib import Path

from tests._consolidate_offset_testkit import (
    KEEP_COUNT,
    Session,
    SessionManager,
    assert_messages_content,
    create_session_with_messages,
    get_old_messages,
)


class TestSessionLastConsolidated:
    def test_initial_last_consolidated_zero(self) -> None:
        session = Session(key="test:initial")
        assert session.last_consolidated == 0

    def test_last_consolidated_persistence(self, tmp_path: Path) -> None:
        manager = SessionManager(Path(tmp_path))
        session = create_session_with_messages("test:persist", 20)
        session.last_consolidated = 15
        manager.save(session)

        reloaded = manager.get_or_create("test:persist")
        assert reloaded.last_consolidated == 15
        assert len(reloaded.messages) == 20

    def test_clear_resets_last_consolidated(self) -> None:
        session = create_session_with_messages("test:clear", 10)
        session.last_consolidated = 5
        session.clear()
        assert session.messages == []
        assert session.last_consolidated == 0


class TestConsolidationTriggerConditions:
    def test_consolidation_needed_when_messages_exceed_window(self) -> None:
        session = create_session_with_messages("test:trigger", 60)
        total_messages = len(session.messages)
        messages_to_process = total_messages - session.last_consolidated

        assert total_messages > 50
        assert messages_to_process > 0
        assert total_messages - KEEP_COUNT == 35

    def test_consolidation_skipped_when_within_keep_count(self) -> None:
        session = create_session_with_messages("test:skip", 20)
        assert len(session.messages) <= KEEP_COUNT
        assert get_old_messages(session, session.last_consolidated, KEEP_COUNT) == []

    def test_consolidation_skipped_when_no_new_messages(self) -> None:
        session = create_session_with_messages("test:already_consolidated", 40)
        session.last_consolidated = len(session.messages) - KEEP_COUNT
        for index in range(40, 42):
            session.add_message("user", f"msg{index}")

        total_messages = len(session.messages)
        assert total_messages - session.last_consolidated > 0

        session.last_consolidated = total_messages - KEEP_COUNT
        assert get_old_messages(session, session.last_consolidated, KEEP_COUNT) == []


class TestLastConsolidatedEdgeCases:
    def test_last_consolidated_exceeds_message_count(self) -> None:
        session = create_session_with_messages("test:corruption", 10)
        session.last_consolidated = 20

        assert len(session.messages) - session.last_consolidated <= 0
        assert get_old_messages(session, session.last_consolidated, 5) == []

    def test_last_consolidated_negative_value(self) -> None:
        session = create_session_with_messages("test:negative", 10)
        session.last_consolidated = -5

        old_messages = get_old_messages(session, session.last_consolidated, 3)
        assert len(old_messages) == 2
        assert_messages_content(old_messages, 5, 6)

    def test_messages_added_after_consolidation(self) -> None:
        session = create_session_with_messages("test:new_messages", 40)
        session.last_consolidated = len(session.messages) - KEEP_COUNT
        for index in range(40, 50):
            session.add_message("user", f"msg{index}")

        old_messages = get_old_messages(session, session.last_consolidated, KEEP_COUNT)
        expected_count = len(session.messages) - KEEP_COUNT - session.last_consolidated
        assert len(old_messages) == expected_count
        assert_messages_content(old_messages, 15, 24)

    def test_slice_behavior_when_indices_overlap(self) -> None:
        session = create_session_with_messages("test:overlap", 30)
        session.last_consolidated = 12
        assert get_old_messages(session, session.last_consolidated, 20) == []
