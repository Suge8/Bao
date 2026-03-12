from __future__ import annotations

import re
from pathlib import Path

QML_DIR = Path(__file__).resolve().parents[1] / "app" / "qml"
_MOUSE_AREA_START = re.compile(r"MouseArea\s*\{", re.M)
_HOVER_HANDLER_START = re.compile(r"HoverHandler\s*\{", re.M)


def _read_qml(name: str) -> str:
    return (QML_DIR / name).read_text(encoding="utf-8")


def _iter_mouse_area_blocks(text: str) -> list[tuple[int, str]]:
    return _iter_blocks(text, _MOUSE_AREA_START)


def _iter_hover_handler_blocks(text: str) -> list[tuple[int, str]]:
    return _iter_blocks(text, _HOVER_HANDLER_START)


def _iter_blocks(text: str, pattern: re.Pattern[str]) -> list[tuple[int, str]]:
    blocks: list[tuple[int, str]] = []
    idx = 0
    while True:
        match = pattern.search(text, idx)
        if match is None:
            return blocks
        start = match.start()
        brace_depth = 0
        body_start = text.find("{", start)
        body_end = body_start
        while body_end < len(text):
            char = text[body_end]
            if char == "{":
                brace_depth += 1
            elif char == "}":
                brace_depth -= 1
                if brace_depth == 0:
                    break
            body_end += 1
        line = text.count("\n", 0, start) + 1
        blocks.append((line, text[start : body_end + 1]))
        idx = body_end + 1


def test_cursor_mouse_areas_are_explicit_hover_owners() -> None:
    offenders: list[str] = []
    for path in sorted(QML_DIR.glob("*.qml")):
        text = path.read_text(encoding="utf-8")
        for line, block in _iter_mouse_area_blocks(text):
            if "cursorShape:" not in block or "hoverEnabled: true" in block:
                continue
            offenders.append(f"{path.name}:{line}")
    assert offenders == [], "MouseArea with cursorShape must also opt into hover: " + ", ".join(
        offenders
    )


def test_settings_controls_do_not_use_hover_overlays_for_cursor() -> None:
    offenders: list[str] = []
    for name in ("SettingsField.qml", "SettingsListField.qml", "SettingsSelect.qml"):
        text = _read_qml(name)
        if "acceptedButtons: Qt.NoButton" in text:
            offenders.append(name)
    assert offenders == [], (
        "Settings controls should let the real control own hover/cursor: " + ", ".join(offenders)
    )


def test_settings_select_uses_mouse_area_cursor_owner() -> None:
    text = _read_qml("SettingsSelect.qml")
    assert "id: comboArea" in text
    assert "cursorShape: Qt.PointingHandCursor" in text


def test_session_item_partitions_main_and_delete_click_areas() -> None:
    text = _read_qml("SessionItem.qml")
    assert (
        "readonly property real deleteHitZoneWidth: deleteBtn.width + deleteBtn.anchors.rightMargin"
        in text
    )
    assert "rightMargin: root.deleteHitZoneWidth - 2" in text
    assert text.count("cursorShape: Qt.PointingHandCursor") >= 2


def test_message_bubble_uses_mouse_area_as_cursor_owner() -> None:
    message_bubble = _read_qml("MessageBubble.qml")
    assert "id: clickArea" in message_bubble
    assert "id: systemClickArea" in message_bubble
    assert message_bubble.count("cursorShape: Qt.PointingHandCursor") >= 2


def test_hover_handlers_do_not_own_cursor_feedback() -> None:
    offenders: list[str] = []
    for path in sorted(QML_DIR.glob("*.qml")):
        text = path.read_text(encoding="utf-8")
        for line, block in _iter_hover_handler_blocks(text):
            if "cursorShape:" in block:
                offenders.append(f"{path.name}:{line}")
    assert offenders == [], (
        "HoverHandler should not own cursor feedback in desktop QML: " + ", ".join(offenders)
    )


def test_clickable_mouse_areas_define_cursor_feedback() -> None:
    offenders: list[str] = []
    for path in sorted(QML_DIR.glob("*.qml")):
        text = path.read_text(encoding="utf-8")
        for line, block in _iter_mouse_area_blocks(text):
            if "onClicked" not in block or "cursorShape:" in block:
                continue
            offenders.append(f"{path.name}:{line}")
    assert offenders == [], (
        "Clickable MouseArea should provide explicit cursor feedback: " + ", ".join(offenders)
    )


def test_sidebar_group_running_dot_avoids_parent_visible_animation_binding() -> None:
    text = _read_qml("SidebarGroupHeader.qml")

    assert "id: groupRunningDot" in text
    assert "running: groupRunningDot.visible" in text
    assert "running: parent.visible" not in text


def test_sidebar_guards_injected_services_at_root() -> None:
    text = _read_qml("Sidebar.qml")

    assert (
        'readonly property bool hasChatService: typeof chatService !== "undefined" && chatService !== null'
        in text
    )
    assert (
        'readonly property bool hasSessionService: typeof sessionService !== "undefined" && sessionService !== null'
        in text
    )
    assert (
        'readonly property bool hasDiagnosticsService: typeof diagnosticsService !== "undefined" && diagnosticsService !== null'
        in text
    )
    assert 'property string currentState: hasChatService ? chatService.state : "idle"' in text
    assert 'property bool isRunning: hasChatService && chatService.state === "running"' in text
    assert 'property bool isStarting: hasChatService && chatService.state === "starting"' in text
    assert 'property bool isError: hasChatService && chatService.state === "error"' in text


def test_main_guards_injected_services_at_root() -> None:
    text = _read_qml("Main.qml")

    assert (
        'readonly property bool hasDesktopPreferences: typeof desktopPreferences !== "undefined" && desktopPreferences !== null'
        in text
    )
    assert (
        'readonly property bool hasConfigService: typeof configService !== "undefined" && configService !== null'
        in text
    )
    assert (
        'readonly property bool hasSessionService: typeof sessionService !== "undefined" && sessionService !== null'
        in text
    )
    assert (
        'readonly property bool hasChatService: typeof chatService !== "undefined" && chatService !== null'
        in text
    )
    assert (
        'readonly property bool hasDiagnosticsService: typeof diagnosticsService !== "undefined" && diagnosticsService !== null'
        in text
    )
