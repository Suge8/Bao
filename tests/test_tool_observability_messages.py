from __future__ import annotations

import asyncio
from pathlib import Path

from bao.bus.events import InboundMessage
from bao.bus.queue import MessageBus
from tests._tool_observability_testkit import (
    FakeLoopResult,
    LoopSpec,
    ToolObservabilityProvider,
    build_loop,
    imessage_message,
    install_fake_run,
    prepare_workspace,
)


def test_process_message_persists_tool_observability_in_session_metadata(tmp_path: Path) -> None:
    prepare_workspace(tmp_path)
    loop = build_loop(tmp_path, LoopSpec(provider=ToolObservabilityProvider(with_tool_calls=False)))

    msg = InboundMessage(channel="telegram", sender_id="u1", chat_id="c1", content="hello")
    out = asyncio.run(loop._process_message(msg))

    assert out is not None
    assert isinstance(out.metadata.get("_tool_observability"), dict)

    session = loop.sessions.get_or_create("telegram:c1")
    last_entry = session.metadata.get("_tool_observability_last")
    diagnostics = loop._runtime_diagnostics.snapshot(max_events=0, max_log_lines=0)
    diagnostics_summary = diagnostics.get("tool_observability", {})
    assert isinstance(last_entry, dict)
    assert last_entry["schema_tool_count_last"] > 0
    assert "_tool_observability_recent" not in session.metadata
    assert isinstance(diagnostics_summary, dict)
    assert diagnostics_summary["schema_tool_count_last"] == last_entry["schema_tool_count_last"]


def test_process_message_localizes_empty_final_fallback(tmp_path: Path) -> None:
    prepare_workspace(tmp_path)
    loop = build_loop(tmp_path, LoopSpec(provider=ToolObservabilityProvider(with_tool_calls=False)))
    install_fake_run(loop, FakeLoopResult(content=None))

    out = asyncio.run(loop._process_message(imessage_message()))
    assert out is not None
    assert out.content == "处理完成。"


def test_process_message_localizes_blank_final_fallback(tmp_path: Path) -> None:
    prepare_workspace(tmp_path)
    loop = build_loop(tmp_path, LoopSpec(provider=ToolObservabilityProvider(with_tool_calls=False)))
    install_fake_run(loop, FakeLoopResult(content="   "))

    out = asyncio.run(loop._process_message(imessage_message()))
    assert out is not None
    assert out.content == "处理完成。"


def test_process_message_progress_keeps_final_outbound(tmp_path: Path) -> None:
    prepare_workspace(tmp_path)
    queue = MessageBus()
    loop = build_loop(
        tmp_path,
        LoopSpec(
            provider=ToolObservabilityProvider(with_tool_calls=False),
            bus=queue,
        ),
    )
    install_fake_run(
        loop,
        FakeLoopResult(
            content="最终结果",
            progress_text='运行这条命令静音：\nosascript -e "set volume output muted true"',
        ),
    )

    out = asyncio.run(loop._process_message(InboundMessage(channel="imessage", sender_id="u1", chat_id="c1", content="帮我静音")))
    assert out is not None
    assert out.content == "最终结果"

    first = asyncio.run(asyncio.wait_for(queue.consume_outbound(), timeout=1.0))
    assert first.metadata.get("_progress") is True
