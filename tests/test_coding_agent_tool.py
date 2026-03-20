import asyncio
import json
from contextvars import ContextVar

from bao.agent.tool_result import ToolTextResult, cleanup_result_file
from bao.agent.tools._coding_agent_cache import DetailRecordInput
from bao.agent.tools._coding_agent_health import CodingBackendHealth
from bao.agent.tools.coding_agent import CodingAgentDetailsTool, CodingAgentTool
from bao.agent.tools.coding_agent_base import BaseCodingDetailsTool, DetailCache


def _run(coro):
    return asyncio.run(coro)


class _DummyBackend:
    def __init__(self) -> None:
        self._context_key: ContextVar[str] = ContextVar("context_key", default="telegram:alice")
        self.calls: list[dict[str, object]] = []

    def set_context(self, channel: str, chat_id: str, session_key: str | None = None) -> None:
        if session_key:
            self._context_key.set(session_key)
            return
        self._context_key.set(f"{channel}:{chat_id}")

    async def execute(self, **kwargs):
        self.calls.append(kwargs)
        return "ok"


def _build_parent() -> CodingAgentTool:
    parent = object.__new__(CodingAgentTool)
    parent._backends = {
        "opencode": _DummyBackend(),
        "codex": _DummyBackend(),
    }
    parent._detail_caches = {
        "opencode": DetailCache(),
        "codex": DetailCache(),
    }
    parent._details_tools = {}
    return parent


def _put_record(cache: DetailCache, *, request_id: str, session_id: str, summary: str) -> None:
    cache.build_detail_record(
        DetailRecordInput(
            request_id=request_id,
            context_key="telegram:alice",
            session_id=session_id,
            project_path="/tmp/proj",
            status="success",
            command_preview="tool run",
            stdout=summary,
            stderr="",
            summary=summary,
            attempts=1,
            duration_ms=10,
            exit_code=0,
        )
    )


def test_coding_agent_details_detects_ambiguous_session_id_across_backends() -> None:
    parent = _build_parent()
    _put_record(
        parent._detail_caches["opencode"],
        request_id="req-oc",
        session_id="sess-shared",
        summary="oc",
    )
    _put_record(
        parent._detail_caches["codex"],
        request_id="req-cx",
        session_id="sess-shared",
        summary="cx",
    )

    tool = CodingAgentDetailsTool(parent)
    out = _run(tool.execute(session_id="sess-shared"))

    assert "Ambiguous session_id across backends" in out
    assert "opencode" in out
    assert "codex" in out


def test_coding_agent_details_allows_backend_filter_for_session_lookup() -> None:
    parent = _build_parent()
    _put_record(
        parent._detail_caches["opencode"],
        request_id="req-oc",
        session_id="sess-shared",
        summary="opencode details",
    )
    _put_record(
        parent._detail_caches["codex"],
        request_id="req-cx",
        session_id="sess-shared",
        summary="codex details",
    )

    tool = CodingAgentDetailsTool(parent)
    out = _run(tool.execute(session_id="sess-shared", agent="codex"))

    assert out.startswith("[codex]")
    assert "codex details" in out


def test_coding_agent_execute_blocks_unhealthy_backend() -> None:
    parent = _build_parent()

    async def _probe_backend(name: str, timeout_seconds: int) -> CodingBackendHealth:
        assert name == "codex"
        assert timeout_seconds == 20
        return CodingBackendHealth(
            backend="codex",
            ready=False,
            error_type="model_not_available",
            message="model not available",
            hints=("Use a supported Codex model.",),
        )

    parent._probe_backend = _probe_backend  # type: ignore[attr-defined]

    out = _run(parent.execute(agent="codex", prompt="do work"))
    payload = json.loads(out)

    assert payload["status"] == "error"
    assert payload["error_type"] == "model_not_available"
    assert "codex" in payload["summary"]
    assert parent._backends["codex"].calls == []
    assert parent._backends["opencode"].calls == []


class _FakeDetailsTool(BaseCodingDetailsTool):
    @property
    def name(self) -> str:
        return "fake_details"

    @property
    def description(self) -> str:
        return "fake details"

    @property
    def _tool_label(self) -> str:
        return "Fake"

    @property
    def _meta_prefix(self) -> str:
        return "FAKE_DETAIL_META"


def test_base_coding_details_returns_file_backed_result_for_large_output() -> None:
    cache = DetailCache()
    payload = "x" * 20000
    cache.build_detail_record(
        DetailRecordInput(
            request_id="req-big",
            context_key="telegram:alice",
            session_id="sess-big",
            project_path="/tmp/proj",
            status="success",
            command_preview="tool run",
            stdout=payload,
            stderr="",
            summary="big output",
            attempts=1,
            duration_ms=10,
            exit_code=0,
        )
    )

    tool = _FakeDetailsTool(detail_cache=cache)
    tool.set_context("telegram", "alice")
    result = _run(tool.execute(request_id="req-big", response_format="text"))

    assert isinstance(result, ToolTextResult)
    assert "Fake details" in result.excerpt
    cleanup_result_file(result)


def test_base_coding_details_returns_file_backed_json_for_large_output() -> None:
    cache = DetailCache()
    payload = "x" * 20000
    cache.build_detail_record(
        DetailRecordInput(
            request_id="req-big-json",
            context_key="telegram:alice",
            session_id="sess-big-json",
            project_path="/tmp/proj",
            status="success",
            command_preview="tool run",
            stdout=payload,
            stderr="",
            summary="big output",
            attempts=1,
            duration_ms=10,
            exit_code=0,
        )
    )

    tool = _FakeDetailsTool(detail_cache=cache)
    tool.set_context("telegram", "alice")
    result = _run(tool.execute(request_id="req-big-json", response_format="json"))

    assert isinstance(result, ToolTextResult)
    assert '"request_id":"req-big-json"' in result.excerpt.replace(" ", "")
    cleanup_result_file(result)


def test_coding_agent_details_fallback_returns_file_backed_result_for_large_output() -> None:
    parent = _build_parent()
    big = "x" * 20000
    parent._detail_caches["codex"].build_detail_record(
        DetailRecordInput(
            request_id="req-big",
            context_key="telegram:alice",
            session_id="sess-big",
            project_path="/tmp/proj",
            status="success",
            command_preview="tool run",
            stdout=big,
            stderr="",
            summary="big output",
            attempts=1,
            duration_ms=10,
            exit_code=0,
        )
    )

    tool = CodingAgentDetailsTool(parent)
    result = _run(tool.execute(session_id="sess-big", agent="codex", max_chars=50000))

    assert isinstance(result, ToolTextResult)
    assert "[codex]" in result.excerpt
    cleanup_result_file(result)
