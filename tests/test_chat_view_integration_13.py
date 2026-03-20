# ruff: noqa: E402, N802, N815, F403, F405, I001
from __future__ import annotations

from tests._chat_view_integration_testkit import *

def test_main_chat_view_composer_reveal_animates_bottom_inset_when_hub_starts(qapp):
    _ = qapp
    from app.backend.chat import ChatMessageModel

    messages_model = ChatMessageModel()
    chat_service = DummyChatService(messages_model, state="starting")
    engine, root = _load_main_window(messages_model=messages_model, chat_service=chat_service)

    try:
        composer = _find_object(root, "composerBar")

        start_inset = float(composer.property("presentedListBottomInset"))
        target_running_inset = float(composer.property("targetListBottomInset"))
        assert start_inset == target_running_inset

        chat_service.setState("running")
        _process(50)

        mid_inset = float(composer.property("presentedListBottomInset"))
        end_target = float(composer.property("targetListBottomInset"))

        assert start_inset < mid_inset < end_target

        _process(420)

        assert abs(float(composer.property("presentedListBottomInset")) - end_target) < 1.0
        assert float(composer.property("opacity")) > 0.98
    finally:
        root.deleteLater()
        engine.deleteLater()
        _process(0)


def test_main_chat_view_pending_user_and_startup_greeting_share_single_bottom_path(qapp):
    _ = qapp
    from app.backend.chat import ChatMessageModel

    messages_model = ChatMessageModel()
    for i in range(20):
        messages_model.append_assistant(f"old {i}", status="done")

    chat_service = DummyChatService(messages_model, state="starting")
    engine, root = _load_main_window(messages_model=messages_model, chat_service=chat_service)

    try:
        message_list = _find_object(root, "chatMessageList")

        for _ in range(6):
            _process(30)

        pending_row = messages_model.append_user("hello", status="pending", client_token="tok")
        chat_service.appendAtBottom.emit(pending_row)
        _wait_until(lambda: bool(message_list.property("bottomPinned")) is True)

        chat_service.setState("running")
        _process(40)

        greeting_row = messages_model.append_assistant(
            "welcome",
            status="done",
            entrance_style="greeting",
            entrance_pending=True,
        )
        chat_service.appendAtBottom.emit(greeting_row)
        _wait_until(
            lambda: float(message_list.property("contentY")) >= _scroll_max_y(message_list) - 2.0
        )

        assert bool(message_list.property("bottomPinned")) is True
        assert float(message_list.property("contentY")) >= _scroll_max_y(message_list) - 2.0
    finally:
        root.deleteLater()
        engine.deleteLater()
        _process(0)


def test_main_chat_view_pending_user_uses_instant_follow_without_programmatic_animation(qapp):
    _ = qapp
    from app.backend.chat import ChatMessageModel

    messages_model = ChatMessageModel()
    for i in range(28):
        messages_model.append_assistant(f"old {i}", status="done")

    engine, root = _load_main_window(messages_model=messages_model)

    try:
        chat_service = engine._test_refs["chat_service"]
        message_list = _find_object(root, "chatMessageList")

        for _ in range(6):
            _process(30)

        _ = message_list.setProperty("contentY", _scroll_max_y(message_list))
        _ = message_list.setProperty("bottomPinned", True)
        _process(30)

        row = messages_model.append_user("hello", status="pending", client_token="tok")
        chat_service.appendAtBottom.emit(row)
        _process(40)

        assert bool(message_list.property("programmaticFollowActive")) is False
        assert bool(message_list.property("bottomPinned")) is True
        assert float(message_list.property("contentY")) >= _scroll_max_y(message_list) - 2.0
    finally:
        root.deleteLater()
        engine.deleteLater()
        _process(0)


def test_main_chat_view_short_pending_user_message_keeps_compact_bubble_width(qapp):
    _ = qapp
    from app.backend.chat import ChatMessageModel

    messages_model = ChatMessageModel()
    engine, root = _load_main_window(messages_model=messages_model)

    try:
        chat_service = engine._test_refs["chat_service"]
        message_list = _find_object(root, "chatMessageList")

        for _ in range(6):
            _process(30)

        row = messages_model.append_user("1", status="pending", client_token="tok")
        chat_service.appendAtBottom.emit(row)
        content_item = message_list.property("contentItem")
        assert isinstance(content_item, QQuickItem)

        def _bubble_bodies() -> list[QQuickItem]:
            found: list[QQuickItem] = []
            queue = list(content_item.childItems())
            while queue:
                current = queue.pop(0)
                if str(current.objectName()) == "bubbleBody":
                    found.append(current)
                queue.extend(current.childItems())
            return found

        _wait_until(lambda: len(_bubble_bodies()) > 0)

        bubbles = _bubble_bodies()
        assert float(bubbles[-1].property("width")) < 120.0
    finally:
        root.deleteLater()
        engine.deleteLater()
        _process(0)


def test_main_chat_view_short_user_cjk_message_stays_on_single_line(qapp):
    _ = qapp
    from app.backend.chat import ChatMessageModel

    messages_model = ChatMessageModel()
    engine, root = _load_main_window(messages_model=messages_model)

    try:
        chat_service = engine._test_refs["chat_service"]
        message_list = _find_object(root, "chatMessageList")

        for _ in range(6):
            _process(30)

        row = messages_model.append_user("你是谁", status="done", client_token="tok")
        chat_service.appendAtBottom.emit(row)
        content_item = message_list.property("contentItem")
        assert isinstance(content_item, QQuickItem)

        def _named_items(name: str) -> list[QQuickItem]:
            found: list[QQuickItem] = []
            queue = list(content_item.childItems())
            while queue:
                current = queue.pop(0)
                if str(current.objectName()) == name:
                    found.append(current)
                queue.extend(current.childItems())
            return found

        _wait_until(lambda: len(_named_items("bubbleBody")) > 0 and len(_named_items("contentText")) > 0)

        bubbles = _named_items("bubbleBody")
        texts = _named_items("contentText")
        assert float(bubbles[-1].property("width")) < 140.0
        assert int(texts[-1].property("lineCount")) == 1
    finally:
        root.deleteLater()
        engine.deleteLater()
        _process(0)


def test_main_chat_view_keyboard_scroll_interrupts_auto_follow_animation(qapp):
    _ = qapp
    from app.backend.chat import ChatMessageModel

    messages_model = ChatMessageModel()
    for i in range(48):
        messages_model.append_user(f"message {i}")

    engine, root = _load_main_window(messages_model=messages_model)

    try:
        chat_service = engine._test_refs["chat_service"]
        message_list = _find_object(root, "chatMessageList")
        root.requestActivate()

        for _ in range(6):
            _process(30)

        _ = message_list.setProperty("contentY", 0.0)
        _process(30)

        row = messages_model.append_user("hello")
        chat_service.appendAtBottom.emit(row)
        _process(40)

        message_list.forceActiveFocus()
        _process(20)
        QTest.keyClick(root, Qt.Key_Home)

        for _ in range(10):
            _process(30)

        assert float(message_list.property("contentY")) < 2.0
    finally:
        root.deleteLater()
        engine.deleteLater()
        _process(0)


def test_main_chat_view_history_merge_with_tool_row_and_final_result_does_not_jump_to_top(qapp):
    _ = qapp
    from app.backend.chat import ChatMessageModel

    raw_history = [{"role": "user", "content": f"message {i}"} for i in range(48)]
    messages_model = ChatMessageModel()
    messages_model.load_prepared(
        ChatMessageModel.prepare_history(
            raw_history
            + [
                {"role": "assistant", "content": "working", "status": "done"},
                {"role": "assistant", "content": "", "status": "typing"},
            ]
        )
    )

    engine, root = _load_main_window(messages_model=messages_model)

    try:
        message_list = _find_object(root, "chatMessageList")

        for _ in range(6):
            _process(30)

        max_y_before = max(
            0.0,
            float(message_list.property("contentHeight")) - float(message_list.property("height")),
        )
        assert max_y_before > 1.0

        _ = message_list.setProperty("contentY", max_y_before)
        _process(30)

        prepared = ChatMessageModel.prepare_history(
            raw_history
            + [
                {"role": "tool", "content": "running tool"},
                {"role": "assistant", "content": "final", "status": "done", "format": "markdown"},
            ]
        )
        messages_model.load_prepared(prepared, preserve_transient_tail=True)

        for _ in range(6):
            _process(30)

        content_y = float(message_list.property("contentY"))
        assert content_y > 2.0
    finally:
        root.deleteLater()
        engine.deleteLater()
        _process(0)
