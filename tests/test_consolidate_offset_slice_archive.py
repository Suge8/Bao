from __future__ import annotations

from tests._consolidate_offset_testkit import (
    KEEP_COUNT,
    _archive_all_signature,
    assert_messages_content,
    create_session_with_messages,
    get_old_messages,
)


class TestArchiveAllMode:
    def test_archive_all_consolidates_everything(self) -> None:
        session = create_session_with_messages("test:archive_all", 50)
        assert len(session.messages) == 50
        assert session.last_consolidated == 0

    def test_archive_all_keeps_last_consolidated_unchanged(self) -> None:
        session = create_session_with_messages("test:reset", 40)
        session.last_consolidated = 15
        assert session.last_consolidated == 15
        assert len(session.messages) == 40

    def test_archive_all_signature_changes_when_messages_change(self) -> None:
        session = create_session_with_messages("test:archive_sig", 2)
        signature_before = _archive_all_signature(session.messages)
        session.add_message("assistant", "tail")
        signature_after = _archive_all_signature(session.messages)

        assert signature_before
        assert signature_after
        assert signature_before != signature_after

    def test_archive_all_signature_stable_without_new_messages(self) -> None:
        session = create_session_with_messages("test:archive_sig_stable", 3)
        assert _archive_all_signature(session.messages) == _archive_all_signature(session.messages)

    def test_archive_all_vs_normal_consolidation(self) -> None:
        normal = create_session_with_messages("test:normal", 60)
        normal.last_consolidated = len(normal.messages) - KEEP_COUNT

        archive_all = create_session_with_messages("test:all", 60)
        assert normal.last_consolidated == 35
        assert archive_all.last_consolidated == 0


class TestCacheImmutability:
    def test_consolidation_does_not_modify_messages_list(self) -> None:
        session = create_session_with_messages("test:immutable", 50)
        original_messages = session.messages.copy()
        session.last_consolidated = len(session.messages) - KEEP_COUNT

        assert session.messages == original_messages

    def test_get_history_does_not_modify_messages(self) -> None:
        session = create_session_with_messages("test:history_immutable", 40)
        original_messages = [message.copy() for message in session.messages]

        for _ in range(5):
            assert len(session.get_history(max_messages=10)) == 10

        for index, message in enumerate(session.messages):
            assert message["content"] == original_messages[index]["content"]

    def test_consolidation_only_updates_last_consolidated(self) -> None:
        session = create_session_with_messages("test:field_only", 60)
        original_messages = session.messages.copy()
        original_key = session.key
        original_metadata = session.metadata.copy()

        session.last_consolidated = len(session.messages) - KEEP_COUNT
        assert session.messages == original_messages
        assert session.key == original_key
        assert session.metadata == original_metadata
        assert session.last_consolidated == 35


class TestSliceLogic:
    def test_slice_extracts_correct_range(self) -> None:
        session = create_session_with_messages("test:slice", 60)
        old_messages = get_old_messages(session, 0, KEEP_COUNT)
        assert len(old_messages) == 35
        assert_messages_content(old_messages, 0, 34)

        remaining = session.messages[-KEEP_COUNT:]
        assert len(remaining) == 25
        assert_messages_content(remaining, 35, 59)

    def test_slice_with_partial_consolidation(self) -> None:
        session = create_session_with_messages("test:partial", 70)
        old_messages = get_old_messages(session, 30, KEEP_COUNT)
        assert len(old_messages) == 15
        assert_messages_content(old_messages, 30, 44)

    def test_slice_with_various_keep_counts(self) -> None:
        session = create_session_with_messages("test:keep_counts", 50)
        for keep_count, expected_count in [(10, 40), (20, 30), (30, 20), (40, 10)]:
            assert len(session.messages[0:-keep_count]) == expected_count

    def test_slice_when_keep_count_exceeds_messages(self) -> None:
        session = create_session_with_messages("test:exceed", 10)
        assert session.messages[0:-20] == []

    def test_very_large_session(self) -> None:
        session = create_session_with_messages("test:large", 1000)
        old_messages = get_old_messages(session, session.last_consolidated, KEEP_COUNT)
        assert len(old_messages) == 975
        assert_messages_content(old_messages, 0, 974)

    def test_session_with_gaps_in_consolidation(self) -> None:
        session = create_session_with_messages("test:gaps", 50)
        session.last_consolidated = 10
        for index in range(50, 60):
            session.add_message("user", f"msg{index}")

        old_messages = get_old_messages(session, session.last_consolidated, KEEP_COUNT)
        assert len(old_messages) == 25
        assert_messages_content(old_messages, 10, 34)
