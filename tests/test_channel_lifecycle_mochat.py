# ruff: noqa: F403, F405
from __future__ import annotations

import json

from tests._channel_lifecycle_testkit import *


@pytest.mark.asyncio
async def test_mochat_start_waits_until_stop() -> None:
    channel = _new_mochat_channel()
    channel._load_session_cursors = AsyncMock()
    channel._refresh_targets = AsyncMock()
    channel._start_socket_client = AsyncMock(return_value=False)
    channel._reconcile_transport_mode = AsyncMock()

    start_task = asyncio.create_task(channel.start())
    await asyncio.sleep(0.05)
    assert not start_task.done()

    await channel.stop()
    await asyncio.wait_for(start_task, timeout=0.5)


@pytest.mark.asyncio
async def test_mochat_transport_mode_reuses_and_clears_fallback_workers() -> None:
    channel = _new_mochat_channel()
    channel._running = True
    channel._session_set = {"s1"}
    channel._panel_set = {"p1"}

    gate = asyncio.Event()
    _install_waiting_mochat_workers(channel, gate)

    await channel._reconcile_transport_mode("fallback")
    session_task = channel._session_fallback_tasks["s1"]
    panel_task = channel._panel_fallback_tasks["p1"]

    await channel._reconcile_transport_mode("fallback")

    assert channel._session_fallback_tasks["s1"] is session_task
    assert channel._panel_fallback_tasks["p1"] is panel_task

    await channel._reconcile_transport_mode("socket")

    assert channel._session_fallback_tasks == {}
    assert channel._panel_fallback_tasks == {}

    gate.set()
    await asyncio.gather(session_task, panel_task, return_exceptions=True)


@pytest.mark.asyncio
async def test_mochat_reconcile_transport_mode_syncs_workers() -> None:
    channel = _new_mochat_channel()
    channel._running = True
    channel._session_set = {"s1"}
    channel._panel_set = {"p1"}
    session_task = asyncio.create_task(asyncio.sleep(60))
    panel_task = asyncio.create_task(asyncio.sleep(60))
    stale_task = asyncio.create_task(asyncio.sleep(60))
    channel._session_fallback_tasks = {"s1": session_task, "stale": stale_task}
    channel._panel_fallback_tasks = {"p1": panel_task}

    created_sessions: list[str] = []
    created_panels: list[str] = []

    async def _session_watch_worker(session_id: str) -> None:
        created_sessions.append(session_id)
        await asyncio.sleep(60)

    async def _panel_poll_worker(panel_id: str) -> None:
        created_panels.append(panel_id)
        await asyncio.sleep(60)

    channel._session_watch_worker = _session_watch_worker
    channel._panel_poll_worker = _panel_poll_worker

    try:
        await channel._reconcile_transport_mode("fallback")
        await asyncio.sleep(0)

        assert channel._transport_mode == "fallback"
        assert list(channel._session_fallback_tasks) == ["s1"]
        assert list(channel._panel_fallback_tasks) == ["p1"]
        assert created_sessions == []
        assert created_panels == []
        assert stale_task.cancelled()

        channel._session_set.add("s2")
        channel._panel_set.add("p2")
        await channel._reconcile_transport_mode("fallback")
        await asyncio.sleep(0)

        assert set(channel._session_fallback_tasks) == {"s1", "s2"}
        assert set(channel._panel_fallback_tasks) == {"p1", "p2"}
        assert created_sessions == ["s2"]
        assert created_panels == ["p2"]

        await channel._reconcile_transport_mode("socket")
        await asyncio.sleep(0)

        assert channel._transport_mode == "socket"
        assert channel._session_fallback_tasks == {}
        assert channel._panel_fallback_tasks == {}
    finally:
        for task in [session_task, panel_task, stale_task]:
            task.cancel()
        await asyncio.gather(session_task, panel_task, stale_task, return_exceptions=True)


@pytest.mark.asyncio
async def test_mochat_load_session_cursors_migrates_legacy_state(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("bao.channels.mochat.get_data_path", lambda: tmp_path)
    channel = MochatChannel(
        MochatConfig(enabled=True, claw_token=SecretStr("tok")),
        MagicMock(),
    )
    legacy_path = tmp_path / "mochat" / "session_cursors.json"
    legacy_path.parent.mkdir(parents=True, exist_ok=True)
    legacy_path.write_text(
        json.dumps({"cursors": {"session-a": 7}}, ensure_ascii=False),
        encoding="utf-8",
    )

    await channel._load_session_cursors()

    assert channel._session_cursor == {"session-a": 7}
    assert channel._cursor_path.exists()
    assert not legacy_path.exists()
