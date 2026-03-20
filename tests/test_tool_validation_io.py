from __future__ import annotations

from pathlib import Path
from typing import Any

from tests._tool_validation_testkit import (
    ExecTool,
    ExecToolOptions,
    ReadFileTool,
    ToolTextResult,
    asyncio,
    cleanup_result_file,
    tempfile,
)


def test_exec_extract_absolute_paths_variants() -> None:
    assert ExecTool._extract_absolute_paths(r"type C:\user\workspace\txt") == [r"C:\user\workspace\txt"]
    assert "/bin/python" not in ExecTool._extract_absolute_paths(".venv/bin/python script.py")
    paths = ExecTool._extract_absolute_paths("cat /tmp/data.txt > /tmp/out.txt")
    assert "/tmp/data.txt" in paths and "/tmp/out.txt" in paths
    assert r"C:\user\my docs\file.txt" in ExecTool._extract_absolute_paths('type "C:\\user\\my docs\\file.txt"')
    assert "/tmp/my folder/data.txt" in ExecTool._extract_absolute_paths("cat '/tmp/my folder/data.txt'")


def test_exec_guards_and_read_only_modes() -> None:
    with tempfile.TemporaryDirectory() as ws_dir, tempfile.TemporaryDirectory() as outside_dir:
        tool = ExecTool(ExecToolOptions(working_dir=ws_dir, restrict_to_workspace=True))
        outside_file = Path(outside_dir) / "my folder" / "data.txt"
        outside_file.parent.mkdir(parents=True, exist_ok=True)
        outside_file.write_text("x", encoding="utf-8")
        result = asyncio.run(tool.execute(command=f"cat '{outside_file.as_posix()}'"))
        assert result == "Error: Command blocked by safety guard (path outside working dir)"

    assert asyncio.run(
        ExecTool(ExecToolOptions(sandbox_mode="read-only")).execute(command="cat /tmp/a | tee /tmp/b")
    ) == "Error: Command blocked by read-only sandbox"
    assert asyncio.run(
        ExecTool(ExecToolOptions(sandbox_mode="read-only")).execute(command="ls > /tmp/out.txt")
    ) == "Error: Command blocked by read-only sandbox"


def test_exec_does_not_truncate_large_output(monkeypatch: Any) -> None:
    payload = "x" * 12050

    class _FakeProcess:
        returncode = 0

        def __init__(self) -> None:
            self.stdout = asyncio.StreamReader()
            self.stderr = asyncio.StreamReader()
            self.stdout.feed_data(payload.encode("utf-8"))
            self.stdout.feed_eof()
            self.stderr.feed_eof()

        async def wait(self) -> int:
            return 0

    async def _fake_create_subprocess_shell(*args: Any, **kwargs: Any) -> _FakeProcess:
        del args, kwargs
        return _FakeProcess()

    monkeypatch.setattr(asyncio, "create_subprocess_shell", _fake_create_subprocess_shell)
    result = asyncio.run(ExecTool().execute(command="printf x"))
    assert isinstance(result, ToolTextResult)
    assert result.chars == len(payload)
    assert result.path.read_text(encoding="utf-8") == payload
    cleanup_result_file(result)


def test_read_file_small_and_large(tmp_path: Path) -> None:
    small = tmp_path / "small.txt"
    small.write_text("hello", encoding="utf-8")
    assert asyncio.run(ReadFileTool(workspace=tmp_path).execute(path="small.txt")) == "hello"

    payload = "x" * 12000
    large = tmp_path / "large.txt"
    large.write_text(payload, encoding="utf-8")
    result = asyncio.run(ReadFileTool(workspace=tmp_path).execute(path="large.txt"))
    assert isinstance(result, ToolTextResult)
    assert result.path == large and result.chars == len(payload) and result.cleanup is False
