from __future__ import annotations

from typing import Any

from loguru import logger

from ._loop_tool_registry_common import ToolRegistrationOptions, register_tool


def register_desktop_tools(loop: Any) -> None:
    if not loop._desktop_config or not loop._desktop_config.enabled:
        return
    tool_specs = _desktop_tool_specs()
    if tool_specs is None:
        return
    for tool, options in tool_specs:
        register_tool(loop, tool, options)
    logger.debug("🖥️ 启用桌面 / desktop enabled: desktop automation tools")


def _desktop_tool_specs() -> tuple[tuple[Any, ToolRegistrationOptions], ...] | None:
    try:
        from bao.agent.tools.desktop import (
            ClickTool,
            DragTool,
            GetScreenInfoTool,
            KeyPressTool,
            ScreenshotTool,
            ScrollTool,
            TypeTextTool,
        )
    except ImportError:
        logger.warning(
            "⚠️ 桌面依赖缺失 / desktop deps missing: mss, pyautogui, pillow are required"
        )
        return None
    primary = _primary_desktop_tool_specs(
        screenshot_tool_cls=ScreenshotTool,
        click_tool_cls=ClickTool,
        type_text_tool_cls=TypeTextTool,
        key_press_tool_cls=KeyPressTool,
    )
    secondary = _secondary_desktop_tool_specs(
        scroll_tool_cls=ScrollTool,
        drag_tool_cls=DragTool,
        get_screen_info_tool_cls=GetScreenInfoTool,
    )
    return primary + secondary


def _primary_desktop_tool_specs(
    *,
    screenshot_tool_cls: Any,
    click_tool_cls: Any,
    type_text_tool_cls: Any,
    key_press_tool_cls: Any,
) -> tuple[tuple[Any, ToolRegistrationOptions], ...]:
    return (
        (
            screenshot_tool_cls(),
            ToolRegistrationOptions(
                bundle="desktop",
                short_hint="Capture the current screen before desktop interaction.",
                aliases=("screenshot", "截图"),
                keyword_aliases=("screen", "screenshot", "截图", "屏幕"),
            ),
        ),
        (
            click_tool_cls(),
            ToolRegistrationOptions(
                bundle="desktop",
                short_hint="Click a desktop coordinate, usually after taking a screenshot.",
                aliases=("click", "点击"),
                keyword_aliases=("click", "点击", "button"),
            ),
        ),
        (
            type_text_tool_cls(),
            ToolRegistrationOptions(
                bundle="desktop",
                short_hint="Type text into the currently focused desktop input.",
                aliases=("type text", "输入文字"),
                keyword_aliases=("type", "input", "输入", "键入"),
            ),
        ),
        (
            key_press_tool_cls(),
            ToolRegistrationOptions(
                bundle="desktop",
                short_hint="Press a key or hotkey on the desktop.",
                aliases=("key press", "按键"),
                keyword_aliases=("key", "hotkey", "按键", "快捷键"),
            ),
        ),
    )


def _secondary_desktop_tool_specs(
    *,
    scroll_tool_cls: Any,
    drag_tool_cls: Any,
    get_screen_info_tool_cls: Any,
) -> tuple[tuple[Any, ToolRegistrationOptions], ...]:
    return (
        (
            scroll_tool_cls(),
            ToolRegistrationOptions(
                bundle="desktop",
                short_hint="Scroll the desktop view.",
                aliases=("scroll", "滚动"),
                keyword_aliases=("scroll", "滚动"),
            ),
        ),
        (
            drag_tool_cls(),
            ToolRegistrationOptions(
                bundle="desktop",
                short_hint="Drag between two desktop coordinates.",
                aliases=("drag", "拖拽"),
                keyword_aliases=("drag", "拖拽"),
            ),
        ),
        (
            get_screen_info_tool_cls(),
            ToolRegistrationOptions(
                bundle="desktop",
                short_hint="Get screen dimensions and mouse position.",
                aliases=("screen info", "屏幕信息"),
                keyword_aliases=("screen", "display", "屏幕", "坐标"),
            ),
        ),
    )
