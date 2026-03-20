# ruff: noqa: F403, F405
from __future__ import annotations

from tests._artifacts_testkit import *


def _load_agent_loop():
    try:
        from bao.agent.loop import AgentLoop
    except ModuleNotFoundError as exc:
        pytest.skip(f"AgentLoop import unavailable in current workspace: {exc}")
    return AgentLoop


def test_process_message_ignores_cleanup_stale_error(tmp_path: Path, monkeypatch) -> None:
    from bao.agent.artifacts import ArtifactStore
    from bao.bus.events import InboundMessage
    from bao.bus.queue import MessageBus

    agent_loop_cls = _load_agent_loop()

    def _raise_cleanup(self: ArtifactStore) -> None:
        raise RuntimeError("cleanup failed")

    monkeypatch.setattr(ArtifactStore, "cleanup_stale", _raise_cleanup)
    (tmp_path / "PERSONA.md").write_text(
        "# Persona\n\n## User\n- **Name**: test\n", encoding="utf-8"
    )
    (tmp_path / "INSTRUCTIONS.md").write_text("# 指令\n", encoding="utf-8")

    loop = agent_loop_cls(
        bus=MessageBus(),
        provider=cast(Any, _StaticProvider()),
        workspace=tmp_path,
        max_iterations=1,
    )
    msg = InboundMessage(channel="hub", sender_id="u", chat_id="c", content="hello")

    response = asyncio.run(loop._process_message(msg))

    assert response is not None
    assert response.content == "ok"
    assert loop._artifact_cleanup_done is True


def test_process_message_uses_session_key_for_artifact_store(tmp_path: Path, monkeypatch) -> None:
    from bao.agent.artifacts import ArtifactStore
    from bao.bus.events import InboundMessage
    from bao.bus.queue import MessageBus

    agent_loop_cls = _load_agent_loop()

    captured: list[str] = []
    original_init = ArtifactStore.__init__

    def _spy_init(self: ArtifactStore, workspace: Path, session_key: str, retention_days: int = 7):
        captured.append(session_key)
        original_init(self, workspace, session_key, retention_days)

    monkeypatch.setattr(ArtifactStore, "__init__", _spy_init)

    (tmp_path / "PERSONA.md").write_text(
        "# Persona\n\n## User\n- **Name**: test\n", encoding="utf-8"
    )
    (tmp_path / "INSTRUCTIONS.md").write_text("# 指令\n", encoding="utf-8")

    loop = agent_loop_cls(
        bus=MessageBus(),
        provider=cast(Any, _StaticProvider()),
        workspace=tmp_path,
        max_iterations=1,
    )
    loop._ctx_mgmt = "auto"

    msg = InboundMessage(channel="hub", sender_id="u", chat_id="c", content="hello")
    response = asyncio.run(loop._process_message(msg))

    assert response is not None
    assert "gateway:c" in captured
