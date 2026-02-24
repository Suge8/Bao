import importlib.util
import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Callable, Protocol, cast

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from bao.utils.helpers import safe_filename


class ArtifactRefLike(Protocol):
    path: Path
    kind: str
    size: int
    redacted: bool


class ArtifactStoreLike(Protocol):
    session_dir: Path

    def write_text(
        self, kind: str, name_hint: str, content: str, *, redacted: bool = False
    ) -> ArtifactRefLike: ...

    def archive_json(self, kind: str, name_hint: str, obj: object) -> ArtifactRefLike: ...

    def format_pointer(
        self, ref: ArtifactRefLike, preview_text: str = "", note: str = ""
    ) -> str: ...

    def cleanup_session(self) -> None: ...

    def cleanup_stale(self) -> None: ...


class ArtifactStoreConstructor(Protocol):
    def __call__(
        self, workspace: Path, session_key: str, retention_days: int = 7
    ) -> ArtifactStoreLike: ...


def _artifact_store_class() -> ArtifactStoreConstructor:
    module_path = PROJECT_ROOT / "bao" / "agent" / "artifacts.py"
    module_name = "_artifact_store_mod"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return cast(ArtifactStoreConstructor, getattr(module, "ArtifactStore"))


def _make_store(tmp_path: Path, session_key: str, retention_days: int = 7) -> ArtifactStoreLike:
    store_cls = _artifact_store_class()
    return store_cls(tmp_path, session_key, retention_days)


def test_write_text_writes_file_with_expected_content(tmp_path: Path) -> None:
    store = _make_store(tmp_path, "telegram:chat/1")

    ref = store.write_text("tool_output", "stdout dump", "hello artifact")

    assert ref.path.exists()
    assert ref.kind == "tool_output"
    assert ref.size == len("hello artifact")
    assert ref.redacted is False
    assert ref.path.read_text(encoding="utf-8") == "hello artifact"
    assert "outputs" in ref.path.parts
    assert safe_filename("telegram:chat/1") in ref.path.parts


def test_archive_json_writes_parseable_json_file(tmp_path: Path) -> None:
    store = _make_store(tmp_path, "session:json")
    payload = {"name": "bao", "count": 2, "items": ["a", "b"]}

    ref = store.archive_json("trajectory", "snapshot", payload)

    assert ref.path.exists()
    assert ref.path.suffix == ".json"
    assert "trajectory" in ref.path.parts
    data = cast(dict[str, object], json.loads(ref.path.read_text(encoding="utf-8")))
    assert data == payload


def test_format_pointer_includes_size_and_paths(tmp_path: Path) -> None:
    store = _make_store(tmp_path, "session:pointer")
    ref = store.write_text("tool_output", "tool run", "abcdef")

    pointer = store.format_pointer(ref, preview_text="preview")

    rel_path = ref.path.relative_to(tmp_path)
    assert f"offloaded: {ref.size} chars" in pointer
    assert str(rel_path) in pointer
    assert str(ref.path.resolve()) in pointer
    assert "preview" in pointer


def test_format_pointer_redacted_hides_full_output_line(tmp_path: Path) -> None:
    store = _make_store(tmp_path, "session:redacted")
    ref = store.write_text("tool_output", "secret-output", "sensitive", redacted=True)

    pointer = store.format_pointer(ref, preview_text="preview")

    assert "redacted: content not stored" in pointer
    assert "ref: secret-output" in pointer
    assert "[Full output:" not in pointer
    assert "preview" in pointer


def test_cleanup_session_removes_current_session_directory(tmp_path: Path) -> None:
    store = _make_store(tmp_path, "session:cleanup")
    _ = store.write_text("evicted_messages", "chunk", "data")

    assert store.session_dir.exists()

    store.cleanup_session()

    assert not store.session_dir.exists()


def test_cleanup_stale_removes_old_directories_only(tmp_path: Path) -> None:
    store = _make_store(tmp_path, "session:retention", retention_days=7)
    context_root = tmp_path / ".bao" / "context"
    old_dir = context_root / "old-session"
    new_dir = context_root / "new-session"
    old_dir.mkdir(parents=True, exist_ok=True)
    new_dir.mkdir(parents=True, exist_ok=True)

    old_time = time.time() - 10 * 24 * 60 * 60
    os.utime(old_dir, (old_time, old_time))

    store.cleanup_stale()

    assert not old_dir.exists()
    assert new_dir.exists()


def test_write_text_with_private_key_is_redacted(tmp_path: Path) -> None:
    store = _make_store(tmp_path, "session:secret")

    ref = store.write_text(
        "tool_output",
        "secret-output",
        "-----BEGIN PRIVATE KEY-----\nabc\n-----END PRIVATE KEY-----",
    )

    assert ref.redacted is True
    assert not ref.path.exists()


def test_write_text_with_normal_content_is_not_redacted(tmp_path: Path) -> None:
    store = _make_store(tmp_path, "session:normal")

    ref = store.write_text("tool_output", "normal-output", "regular log line")

    assert ref.redacted is False
    assert ref.path.exists()


def test_write_text_with_edit_file_name_hint_is_redacted(tmp_path: Path) -> None:
    store = _make_store(tmp_path, "session:deny")

    ref = store.write_text("tool_output", "edit_file_result", "non-sensitive content")

    assert ref.redacted is True
    assert not ref.path.exists()


def test_is_sensitive_matches_aws_key() -> None:
    store_cls = _artifact_store_class()
    is_sensitive = cast(Callable[[str], bool], getattr(store_cls, "_is_sensitive"))

    assert is_sensitive("AKIAIOSFODNN7EXAMPLE") is True


def test_delete_session_removes_artifact_directory(tmp_path: Path) -> None:
    from bao.session.manager import SessionManager

    manager = SessionManager(tmp_path)
    key = "telegram:chat/1"
    store = _make_store(tmp_path, key)
    _ = store.write_text("tool_output", "stdout", "artifact")
    assert store.session_dir.exists()

    deleted = manager.delete_session(key)

    assert deleted is True
    assert not store.session_dir.exists()


class _StaticProvider:
    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.1,
    ):
        del messages, tools, model, max_tokens, temperature
        from bao.providers.base import LLMResponse

        return LLMResponse(content="ok", finish_reason="stop")

    def get_default_model(self) -> str:
        return "test-model"


def test_process_message_ignores_cleanup_stale_error(tmp_path: Path, monkeypatch) -> None:
    from bao.agent.artifacts import ArtifactStore
    from bao.agent.loop import AgentLoop
    from bao.bus.events import InboundMessage
    from bao.bus.queue import MessageBus

    def _raise_cleanup(self: ArtifactStore) -> None:
        raise RuntimeError("cleanup failed")

    monkeypatch.setattr(ArtifactStore, "cleanup_stale", _raise_cleanup)
    (tmp_path / "PERSONA.md").write_text(
        "# Persona\n\n## User\n- **Name**: test\n", encoding="utf-8"
    )
    (tmp_path / "INSTRUCTIONS.md").write_text("# 指令\n", encoding="utf-8")

    loop = AgentLoop(
        bus=MessageBus(),
        provider=cast(Any, _StaticProvider()),
        workspace=tmp_path,
        max_iterations=1,
    )
    msg = InboundMessage(channel="gateway", sender_id="u", chat_id="c", content="hello")

    response = asyncio.run(loop._process_message(msg))

    assert response is not None
    assert response.content == "ok"
    assert loop._artifact_cleanup_done is True
