import asyncio
import tempfile
from pathlib import Path
from typing import Any

from bao.agent.tool_result import ToolTextResult, cleanup_result_file
from bao.agent.tools.base import Tool
from bao.agent.tools.filesystem import ReadFileTool
from bao.agent.tools.registry import ToolRegistry
from bao.agent.tools.shell import ExecTool


class SampleTool(Tool):
    @property
    def name(self) -> str:
        return "sample"

    @property
    def description(self) -> str:
        return "sample tool"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {"type": "string", "minLength": 2},
                "count": {"type": "integer", "minimum": 1, "maximum": 10},
                "mode": {"type": "string", "enum": ["fast", "full"]},
                "meta": {
                    "type": "object",
                    "properties": {
                        "tag": {"type": "string"},
                        "flags": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                    "required": ["tag"],
                },
            },
            "required": ["query", "count"],
        }

    async def execute(self, **kwargs: Any) -> str:
        return "ok"


def test_validate_params_missing_required() -> None:
    tool = SampleTool()
    errors = tool.validate_params({"query": "hi"})
    assert "missing required count" in "; ".join(errors)


def test_validate_params_type_and_range() -> None:
    tool = SampleTool()
    errors = tool.validate_params({"query": "hi", "count": 0})
    assert any("count must be >= 1" in e for e in errors)

    errors = tool.validate_params({"query": "hi", "count": "2"})
    assert any("count should be integer" in e for e in errors)


def test_validate_params_enum_and_min_length() -> None:
    tool = SampleTool()
    errors = tool.validate_params({"query": "h", "count": 2, "mode": "slow"})
    assert any("query must be at least 2 chars" in e for e in errors)
    assert any("mode must be one of" in e for e in errors)


def test_validate_params_nested_object_and_array() -> None:
    tool = SampleTool()
    errors = tool.validate_params(
        {
            "query": "hi",
            "count": 2,
            "meta": {"flags": [1, "ok"]},
        }
    )
    assert any("missing required meta.tag" in e for e in errors)
    assert any("meta.flags[0] should be string" in e for e in errors)


def test_validate_params_ignores_unknown_fields() -> None:
    tool = SampleTool()
    errors = tool.validate_params({"query": "hi", "count": 2, "extra": "x"})
    assert errors == []


async def test_registry_returns_validation_error() -> None:
    reg = ToolRegistry()
    reg.register(SampleTool())
    result = await reg.execute("sample", {"query": "hi"})
    assert "Invalid parameters" in result


async def test_registry_unknown_tool_shows_available() -> None:
    reg = ToolRegistry()
    reg.register(SampleTool())
    result = await reg.execute("nonexistent_tool", {})
    assert "Available" in result
    assert "sample" in result
    assert "[Analyze the error" in result


def test_exec_extract_absolute_paths_keeps_full_windows_path() -> None:
    cmd = r"type C:\user\workspace\txt"
    paths = ExecTool._extract_absolute_paths(cmd)
    assert paths == [r"C:\user\workspace\txt"]


def test_exec_extract_absolute_paths_ignores_relative_posix_segments() -> None:
    cmd = ".venv/bin/python script.py"
    paths = ExecTool._extract_absolute_paths(cmd)
    assert "/bin/python" not in paths


def test_exec_extract_absolute_paths_captures_posix_absolute_paths() -> None:
    cmd = "cat /tmp/data.txt > /tmp/out.txt"
    paths = ExecTool._extract_absolute_paths(cmd)
    assert "/tmp/data.txt" in paths
    assert "/tmp/out.txt" in paths


def test_exec_extract_absolute_paths_keeps_quoted_windows_path_with_spaces() -> None:
    cmd = 'type "C:\\user\\my docs\\file.txt"'
    paths = ExecTool._extract_absolute_paths(cmd)
    assert r"C:\user\my docs\file.txt" in paths


def test_exec_extract_absolute_paths_keeps_quoted_posix_path_with_spaces() -> None:
    cmd = "cat '/tmp/my folder/data.txt'"
    paths = ExecTool._extract_absolute_paths(cmd)
    assert "/tmp/my folder/data.txt" in paths


def test_exec_workspace_guard_blocks_quoted_absolute_posix_path_with_spaces() -> None:
    with tempfile.TemporaryDirectory() as ws_dir, tempfile.TemporaryDirectory() as outside_dir:
        tool = ExecTool(working_dir=ws_dir, restrict_to_workspace=True)
        outside_file = Path(outside_dir) / "my folder" / "data.txt"
        outside_file.parent.mkdir(parents=True, exist_ok=True)
        outside_file.write_text("x", encoding="utf-8")

        cmd = f"cat '{outside_file.as_posix()}'"
        result = asyncio.run(tool.execute(command=cmd))
        assert result == "Error: Command blocked by safety guard (path outside working dir)"


def test_exec_read_only_blocks_tee_write() -> None:
    tool = ExecTool(sandbox_mode="read-only")
    result = asyncio.run(tool.execute(command="cat /tmp/a | tee /tmp/b"))
    assert result == "Error: Command blocked by read-only sandbox"


def test_exec_read_only_blocks_redirect_write() -> None:
    tool = ExecTool(sandbox_mode="read-only")
    result = asyncio.run(tool.execute(command="ls > /tmp/out.txt"))
    assert result == "Error: Command blocked by read-only sandbox"


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

    tool = ExecTool()
    result = asyncio.run(tool.execute(command="printf x"))

    assert isinstance(result, ToolTextResult)
    assert result.chars == len(payload)
    assert result.path.read_text(encoding="utf-8") == payload
    cleanup_result_file(result)


def test_read_file_keeps_small_text_inline(tmp_path: Path) -> None:
    target = tmp_path / "small.txt"
    target.write_text("hello", encoding="utf-8")

    tool = ReadFileTool(workspace=tmp_path)
    result = asyncio.run(tool.execute(path="small.txt"))

    assert result == "hello"


def test_read_file_returns_file_backed_result_for_large_text(tmp_path: Path) -> None:
    payload = "x" * 12000
    target = tmp_path / "large.txt"
    target.write_text(payload, encoding="utf-8")

    tool = ReadFileTool(workspace=tmp_path)
    result = asyncio.run(tool.execute(path="large.txt"))

    assert isinstance(result, ToolTextResult)
    assert result.path == target
    assert result.chars == len(payload)
    assert result.cleanup is False


class CastTestTool(Tool):
    def __init__(self, schema: dict[str, Any]) -> None:
        self._schema = schema

    @property
    def name(self) -> str:
        return "cast_test"

    @property
    def description(self) -> str:
        return "cast test"

    @property
    def parameters(self) -> dict[str, Any]:
        return self._schema

    async def execute(self, **kwargs: Any) -> str:
        return str(kwargs)


def test_cast_params_string_scalars_and_nested_values() -> None:
    tool = CastTestTool(
        {
            "type": "object",
            "properties": {
                "count": {"type": "integer"},
                "rate": {"type": "number"},
                "enabled": {"type": "boolean"},
                "meta": {
                    "type": "object",
                    "properties": {
                        "port": {"type": "integer"},
                        "flags": {"type": "array", "items": {"type": "boolean"}},
                    },
                },
            },
        }
    )

    result = tool.cast_params(
        {
            "count": "42",
            "rate": "3.14",
            "enabled": "false",
            "meta": {"port": "8080", "flags": ["true", "0"]},
        }
    )

    assert result["count"] == 42
    assert result["rate"] == 3.14
    assert result["enabled"] is False
    assert result["meta"]["port"] == 8080
    assert result["meta"]["flags"] == [True, False]


def test_cast_params_does_not_apply_unsafe_conversions() -> None:
    tool = CastTestTool(
        {
            "type": "object",
            "properties": {
                "count": {"type": "integer"},
                "items": {"type": "array"},
                "config": {"type": "object"},
                "flag": {"type": "boolean"},
            },
        }
    )

    result = tool.cast_params(
        {
            "count": True,
            "items": "hello",
            "config": "",
            "flag": "maybe",
        }
    )

    assert result["count"] is True
    assert result["items"] == "hello"
    assert result["config"] == ""
    assert result["flag"] == "maybe"

    errors = tool.validate_params(result)
    joined = "; ".join(errors)
    assert "count should be integer" in joined
    assert "items should be array" in joined
    assert "config should be object" in joined
    assert "flag should be boolean" in joined


async def test_registry_auto_casts_before_validation() -> None:
    reg = ToolRegistry()
    reg.register(
        CastTestTool(
            {
                "type": "object",
                "properties": {
                    "count": {"type": "integer"},
                    "enabled": {"type": "boolean"},
                },
                "required": ["count", "enabled"],
            }
        )
    )

    result = await reg.execute("cast_test", {"count": "7", "enabled": "true"})

    assert "'count': 7" in result
    assert "'enabled': True" in result
