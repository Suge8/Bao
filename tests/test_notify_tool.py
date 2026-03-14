import asyncio
import importlib

from bao.agent.tools.notify import NotifyTool
from bao.bus.events import OutboundMessage

pytest = importlib.import_module("pytest")


def test_notify_tool_requires_explicit_target() -> None:
    sent: list[OutboundMessage] = []

    async def _send_callback(msg: OutboundMessage) -> None:
        sent.append(msg)

    tool = NotifyTool(send_callback=_send_callback)

    async def _run() -> str:
        return await tool.execute(content="hello")

    result = asyncio.run(_run())
    assert result == "Error: notify requires explicit channel and chat_id."
    assert sent == []


def test_notify_tool_rejects_current_session_target() -> None:
    sent: list[OutboundMessage] = []

    async def _send_callback(msg: OutboundMessage) -> None:
        sent.append(msg)

    tool = NotifyTool(send_callback=_send_callback)
    tool.set_context("telegram", "100")

    async def _run() -> str:
        return await tool.execute(channel="telegram", chat_id="100", content="hello")

    result = asyncio.run(_run())
    assert (
        result
        == "Error: notify is only for explicit external delivery. Use the normal reply path for the current session."
    )
    assert sent == []


def test_notify_tool_rejects_desktop_target() -> None:
    tool = NotifyTool(send_callback=lambda _msg: asyncio.sleep(0))

    async def _run() -> str:
        return await tool.execute(channel="desktop", chat_id="local", content="hello")

    result = asyncio.run(_run())
    assert result == "Error: notify cannot send to desktop. Reply through the normal desktop path."


def test_notify_tool_sends_external_notification() -> None:
    sent: list[OutboundMessage] = []

    async def _send_callback(msg: OutboundMessage) -> None:
        sent.append(msg)

    tool = NotifyTool(send_callback=_send_callback)

    async def _run() -> str:
        return await tool.execute(
            channel="telegram",
            chat_id="100",
            content="hello",
            media=["/tmp/a.png"],
        )

    result = asyncio.run(_run())
    assert result == "Notification sent to telegram:100 +1 files: hello"
    assert len(sent) == 1
    assert sent[0].content == "hello"
    assert sent[0].media == ["/tmp/a.png"]


def test_notify_tool_normalizes_target_and_reply_to() -> None:
    sent: list[OutboundMessage] = []

    async def _send_callback(msg: OutboundMessage) -> None:
        sent.append(msg)

    tool = NotifyTool(send_callback=_send_callback)

    async def _run() -> None:
        await tool.execute(channel=" Slack ", chat_id=" C123 ", reply_to="m1", content="x")

    asyncio.run(_run())
    assert len(sent) == 1
    assert sent[0].channel == "slack"
    assert sent[0].chat_id == "C123"
    assert sent[0].reply_to == "m1"


def test_notify_tool_propagates_cancelled_error() -> None:
    async def _send_callback(_msg: OutboundMessage) -> None:
        raise asyncio.CancelledError()

    tool = NotifyTool(send_callback=_send_callback)

    async def _run() -> None:
        await tool.execute(channel="telegram", chat_id="100", content="cancel me")

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(_run())
