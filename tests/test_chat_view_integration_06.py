# ruff: noqa: E402, N802, N815, F403, F405, I001
from __future__ import annotations

from tests._chat_view_integration_testkit import *

def test_hub_capsule_space_key_triggers_hub_action(qapp):
    _ = qapp

    class HubActionChatService(DummyChatService):
        def __init__(self, messages: QAbstractListModel) -> None:
            super().__init__(messages)
            self.start_calls = 0

        @Property(str, constant=True)
        def state(self) -> str:
            return "idle"

        @Slot()
        def start(self) -> None:
            self.start_calls += 1

    session_model = SessionsModel(
        [
            {
                "key": "desktop:local::default",
                "title": "Default",
                "updated_at": "2026-03-06T10:00:00",
                "channel": "desktop",
                "has_unread": False,
            }
        ]
    )
    chat_service = HubActionChatService(EmptyMessagesModel())
    engine, root = _load_main_window(session_model=session_model, chat_service=chat_service)

    try:
        capsule = _find_object(root, "hubCapsule")
        capsule.forceActiveFocus()
        _process(20)

        assert bool(capsule.property("activeFocus")) is True

        QTest.keyClick(root, Qt.Key_Space)
        _process(20)

        assert chat_service.start_calls == 1
    finally:
        root.deleteLater()
        engine.deleteLater()
        _process(0)


def test_hub_capsule_handoffs_starting_motion_into_running_state(qapp):
    _ = qapp

    session_model = SessionsModel(
        [
            {
                "key": "desktop:local::default",
                "title": "Default",
                "updated_at": "2026-03-06T10:00:00",
                "channel": "desktop",
                "has_unread": False,
            }
        ]
    )
    chat_service = DummyChatService(EmptyMessagesModel(), state="starting")
    engine, root = _load_main_window(session_model=session_model, chat_service=chat_service)

    try:
        capsule = _find_object(root, "hubCapsule")
        icon_wrap = _find_object(root, "hubActionIconWrap")

        _process(120)
        starting_turn = float(capsule.property("iconTurn"))
        assert starting_turn > 0.0

        chat_service.setState("running")
        _process(40)

        mid_turn = float(icon_wrap.property("rotation"))
        mid_pulse = float(capsule.property("iconPulse"))

        assert mid_turn > 0.0
        assert mid_pulse > 0.0

        _process(360)

        assert abs(float(icon_wrap.property("rotation"))) < starting_turn
    finally:
        root.deleteLater()
        engine.deleteLater()
        _process(0)


def test_hub_capsule_primary_label_crossfades_between_states(qapp):
    _ = qapp

    session_model = SessionsModel(
        [
            {
                "key": "desktop:local::default",
                "title": "Default",
                "updated_at": "2026-03-06T10:00:00",
                "channel": "desktop",
                "has_unread": False,
            }
        ]
    )
    chat_service = DummyChatService(EmptyMessagesModel(), state="idle")
    engine, root = _load_main_window(session_model=session_model, chat_service=chat_service)

    try:
        incoming = _find_object(root, "hubPrimaryLabelIncoming")
        outgoing = _find_object(root, "hubPrimaryLabelOutgoing")

        assert str(incoming.property("text")) != ""
        chat_service.setState("starting")
        _process(40)

        assert 0.0 < float(incoming.property("opacity")) < 1.0
        assert 0.0 < float(outgoing.property("opacity")) < 1.0

        _wait_until(
            lambda: float(incoming.property("opacity")) > 0.98
            and float(outgoing.property("opacity")) < 0.02,
            attempts=30,
            step_ms=20,
        )

        assert float(incoming.property("opacity")) > 0.98
        assert float(outgoing.property("opacity")) < 0.02
    finally:
        root.deleteLater()
        engine.deleteLater()
        _process(0)


def test_session_switch_animates_only_chat_detail_stage(qapp):
    _ = qapp

    session_model = SessionsModel(
        [
            {
                "key": "desktop:local::default",
                "title": "Default",
                "updated_at": "2026-03-06T10:00:00",
                "channel": "desktop",
                "has_unread": False,
            },
            {
                "key": "desktop:local::second",
                "title": "Second",
                "updated_at": "2026-03-06T10:01:00",
                "channel": "desktop",
                "has_unread": False,
            },
        ]
    )
    engine, root = _load_main_window(session_model=session_model)

    try:
        session_service = engine._test_refs["session_service"]
        rail = _find_object(root, "sessionRailStage")
        detail = _find_object(root, "chatDetailStage")

        _process(60)
        session_service.setActiveKey("desktop:local::second")
        _process(40)

        assert float(rail.property("opacity")) > 0.98
        assert float(detail.property("opacity")) < 1.0

        _process(360)

        assert float(rail.property("opacity")) > 0.98
        assert float(detail.property("opacity")) > 0.98
    finally:
        root.deleteLater()
        engine.deleteLater()
        _process(0)


def test_workspace_nav_highlight_slides_between_sections(qapp):
    _ = qapp

    session_model = SessionsModel(
        [
            {
                "key": "desktop:local::default",
                "title": "Default",
                "updated_at": "2026-03-06T10:00:00",
                "channel": "desktop",
                "has_unread": False,
            }
        ]
    )
    engine, root = _load_main_window(session_model=session_model)

    try:
        highlight = _find_object(root, "sidebarNavHighlight")
        _process(60)

        before_y = float(highlight.property("y"))
        root.setProperty("activeWorkspace", "tools")
        _process(40)
        mid_y = float(highlight.property("y"))
        _process(320)
        final_y = float(highlight.property("y"))

        assert before_y != final_y
        assert min(before_y, final_y) < mid_y < max(before_y, final_y)
    finally:
        root.deleteLater()
        engine.deleteLater()
        _process(0)


def test_cron_workspace_loads_real_panels(qapp):
    _ = qapp

    session_model = SessionsModel(
        [
            {
                "key": "desktop:local::default",
                "title": "Default",
                "updated_at": "2026-03-06T10:00:00",
                "channel": "desktop",
                "has_unread": False,
            }
        ]
    )
    engine, root = _load_main_window(session_model=session_model)

    try:
        root.setProperty("activeWorkspace", "cron")
        _process(120)

        cron_root = _find_object(root, "cronWorkspaceRoot")
        list_panel = _find_object(root, "cronListPanel")
        detail_panel = _find_object(root, "cronDetailPanel")
        status_panel = _find_object(root, "cronStatusPanel")

        assert cron_root.property("visible") is True
        assert float(list_panel.property("width")) > 0
        assert float(detail_panel.property("width")) > 0
        assert float(status_panel.property("width")) > 0
    finally:
        root.deleteLater()
        engine.deleteLater()
        _process(0)
