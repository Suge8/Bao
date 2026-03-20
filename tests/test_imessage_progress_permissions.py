# ruff: noqa: F403, F405
# ruff: noqa: F403, F405
from __future__ import annotations

from tests._imessage_progress_testkit import *


def test_permission_target_label_uses_app_name() -> None:
    assert PERMISSION_TARGET_LABEL("/Applications/Bao.app/Contents/MacOS/Bao") == "Bao"


def test_automation_permission_hint_detects_tcc_denial() -> None:
    result = AUTOMATION_PERMISSION_HINT(
        "51:92: execution error: 未获得授权将Apple事件发送给Messages。 (-1743)",
        "/Applications/Bao.app/Contents/MacOS/Bao",
    )

    assert result is not None
    assert "Automation" in result
    assert "Messages" in result
    assert "Bao" in result


def test_automation_permission_hint_ignores_other_errors() -> None:
    assert AUTOMATION_PERMISSION_HINT("some other osascript error", "/tmp/Bao") is None


def test_imessage_send_raises_on_automation_denied(monkeypatch) -> None:
    async def _fake_exec(*args, **kwargs):
        del args, kwargs
        return _FailingProc(
            b"51:92: execution error: \xe6\x9c\xaa\xe8\x8e\xb7\xe5\xbe\x97\xe6\x8e\x88\xe6\x9d\x83\xe5\xb0\x86Apple\xe4\xba\x8b\xe4\xbb\xb6\xe5\x8f\x91\xe9\x80\x81\xe7\xbb\x99Messages\xe3\x80\x82 (-1743)"
        )

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_exec)

    channel = IMessageChannel(IMessageConfig(enabled=True), MessageBus())

    async def _run() -> None:
        with pytest.raises(RuntimeError, match="-1743"):
            await channel.send(
                OutboundMessage(channel="imessage", chat_id="+86100", content="你好")
            )

    asyncio.run(_run())
