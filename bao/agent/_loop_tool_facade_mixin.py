from __future__ import annotations

from bao.agent._loop_tool_setup import ToolContextRequest
from bao.agent._loop_tool_setup import (
    register_default_tools_with_optionals as _register_default_tools_impl,
)
from bao.agent._loop_tool_setup import register_tool as _register_tool_impl
from bao.agent._loop_tool_setup import set_tool_context as _set_tool_context_impl
from bao.agent._loop_tool_setup import update_tool_metadata as _update_tool_metadata_impl
from bao.agent.tools.base import Tool

from ._loop_tool_registry_common import ToolRegistrationOptions


class LoopToolFacadeMixin:
    def _register_tool(self, tool: Tool, options: ToolRegistrationOptions) -> None: _register_tool_impl(self, tool, options)
    def _update_tool_metadata(self, name: str, *, short_hint: str | None = None) -> None: _update_tool_metadata_impl(self, name, short_hint=short_hint)
    def _register_default_tools(self) -> None: _register_default_tools_impl(self)
    def _set_tool_context(self, request: ToolContextRequest) -> None: _set_tool_context_impl(self, request)
    def set_delivery_sender(self, sender) -> None: self._delivery_sender = sender
