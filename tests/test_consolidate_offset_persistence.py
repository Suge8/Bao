from __future__ import annotations

from pathlib import Path

from tests._consolidate_offset_testkit import Session, SessionManager, create_session_with_messages


class TestSessionPersistence:
    def test_persistence_roundtrip(self, tmp_path: Path) -> None:
        manager = SessionManager(Path(tmp_path))
        session = create_session_with_messages("test:persistence", 20)
        manager.save(session)

        reloaded = manager.get_or_create("test:persistence")
        assert len(reloaded.messages) == 20
        assert reloaded.messages[0]["content"] == "msg0"
        assert reloaded.messages[-1]["content"] == "msg19"

    def test_get_history_after_reload(self, tmp_path: Path) -> None:
        manager = SessionManager(Path(tmp_path))
        session = create_session_with_messages("test:reload", 30)
        manager.save(session)

        history = manager.get_or_create("test:reload").get_history(max_messages=10)
        assert len(history) == 10
        assert history[0]["content"] == "msg20"
        assert history[-1]["content"] == "msg29"

    def test_persistence_rewrites_when_middle_message_changes(self, tmp_path: Path) -> None:
        manager = SessionManager(Path(tmp_path))
        session = Session("test:rewrite-middle")
        session.add_message("user", "msg0")
        session.add_message("assistant", "msg1")
        session.add_message("user", "msg2")
        manager.save(session)

        session.messages[1]["content"] = "msg1-updated"
        manager.save(session)
        manager.invalidate("test:rewrite-middle")

        reloaded = manager.get_or_create("test:rewrite-middle")
        assert [message["content"] for message in reloaded.messages] == ["msg0", "msg1-updated", "msg2"]

    def test_clear_resets_session(self, tmp_path: Path) -> None:
        del tmp_path
        session = create_session_with_messages("test:clear", 10)
        session.clear()
        assert session.messages == []
