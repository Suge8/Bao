# ruff: noqa: F403, F405
from __future__ import annotations

from bao.agent.artifacts_models import WriteArtifactFileRequest
from tests._artifacts_testkit import *


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
    payload = {"name": "Bao", "count": 2, "items": ["a", "b"]}

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


def test_write_text_file_moves_existing_text_file(tmp_path: Path) -> None:
    store = _make_store(tmp_path, "session:file")
    source = tmp_path / "source.txt"
    source.write_text("streamed artifact", encoding="utf-8")

    ref = store.write_text_file(
        WriteArtifactFileRequest(
            kind="tool_output",
            name_hint="streamed",
            source_path=source,
            size=len("streamed artifact"),
        )
    )

    assert ref.redacted is False
    assert ref.path.exists()
    assert ref.path.read_text(encoding="utf-8") == "streamed artifact"
    assert not source.exists()


def test_write_text_file_can_copy_without_removing_source(tmp_path: Path) -> None:
    store = _make_store(tmp_path, "session:file-copy")
    source = tmp_path / "source-copy.txt"
    source.write_text("persistent artifact", encoding="utf-8")

    ref = store.write_text_file(
        WriteArtifactFileRequest(
            kind="tool_output",
            name_hint="persistent",
            source_path=source,
            size=len("persistent artifact"),
            move_source=False,
        )
    )

    assert ref.redacted is False
    assert ref.path.exists()
    assert ref.path.read_text(encoding="utf-8") == "persistent artifact"
    assert source.exists()


def test_is_sensitive_matches_aws_key() -> None:
    store_cls = _artifact_store_class()
    is_sensitive = cast(Callable[[str], bool], getattr(store_cls, "_is_sensitive"))

    assert is_sensitive("AKIAIOSFODNN7EXAMPLE") is True
