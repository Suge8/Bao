import asyncio
from contextvars import ContextVar

from bao.agent.tools.coding_agent import CodingAgentDetailsTool, CodingAgentTool
from bao.agent.tools.coding_agent_base import DetailCache


def _run(coro):
    return asyncio.run(coro)


class _DummyBackend:
    def __init__(self) -> None:
        self._context_key: ContextVar[str] = ContextVar("context_key", default="telegram:alice")

    def set_context(self, channel: str, chat_id: str, session_key: str | None = None) -> None:
        if session_key:
            self._context_key.set(session_key)
            return
        self._context_key.set(f"{channel}:{chat_id}")


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
