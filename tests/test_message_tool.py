import asyncio

from bao.agent.tools.message import MessageTool
from bao.bus.events import OutboundMessage


def test_message_tool_allows_only_one_send_per_turn() -> None:
    sent: list[OutboundMessage] = []

    async def _send_callback(msg: OutboundMessage) -> None:
        sent.append(msg)

    tool = MessageTool(
        send_callback=_send_callback,
        default_channel="imessage",
        default_chat_id="+86100",
    )

    async def _run() -> tuple[str, str]:
        first = await tool.execute(content="hello")
        second = await tool.execute(content="hello again")
        return first, second

    first, second = asyncio.run(_run())
    assert len(sent) == 1
    assert first.startswith("Message sent to imessage:+86100")
    assert (
        second == "Error: message tool already sent once in this turn. Do not call message again."
    )


def test_message_tool_reset_on_new_turn() -> None:
    sent: list[OutboundMessage] = []

    async def _send_callback(msg: OutboundMessage) -> None:
        sent.append(msg)

    tool = MessageTool(
        send_callback=_send_callback,
        default_channel="imessage",
        default_chat_id="+86100",
    )

    async def _run() -> None:
        await tool.execute(content="turn1")
        tool.start_turn()
        await tool.execute(content="turn2")

    asyncio.run(_run())
    assert len(sent) == 2
    assert sent[0].content == "turn1"
    assert sent[1].content == "turn2"


def test_message_tool_ignores_non_string_default_message_id() -> None:
    sent: list[OutboundMessage] = []

    async def _send_callback(msg: OutboundMessage) -> None:
        sent.append(msg)

    tool = MessageTool(send_callback=_send_callback)
    tool.set_context("telegram", "100", 123)  # type: ignore[arg-type]

    async def _run() -> None:
        await tool.execute(channel="discord", chat_id="chan-1", content="x")

    asyncio.run(_run())
    assert len(sent) == 1
    assert sent[0].reply_to is None
    assert sent[0].metadata.get("message_id") is None


def test_message_tool_does_not_leak_default_reply_to_across_channels() -> None:
    sent: list[OutboundMessage] = []

    async def _send_callback(msg: OutboundMessage) -> None:
        sent.append(msg)

    tool = MessageTool(send_callback=_send_callback)
    tool.set_context("telegram", "100", "123")

    async def _run() -> None:
        await tool.execute(channel="discord", chat_id="chan-1", content="x")

    asyncio.run(_run())
    assert len(sent) == 1
    assert sent[0].reply_to is None


def test_message_tool_keeps_default_reply_to_in_same_context() -> None:
    sent: list[OutboundMessage] = []

    async def _send_callback(msg: OutboundMessage) -> None:
        sent.append(msg)

    tool = MessageTool(send_callback=_send_callback)
    tool.set_context("telegram", "100", "123")

    async def _run() -> None:
        await tool.execute(content="x")

    asyncio.run(_run())
    assert len(sent) == 1
    assert sent[0].reply_to == "123"
    assert sent[0].metadata.get("message_id") == "123"
