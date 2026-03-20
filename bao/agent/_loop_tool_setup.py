from __future__ import annotations

from ._loop_tool_context import ToolContextRequest as _ToolContextRequest
from ._loop_tool_context import set_tool_context as _set_tool_context
from ._loop_tool_registry_common import (
    register_default_tools as _register_default_tools,
)
from ._loop_tool_registry_common import (
    register_tool as _register_tool,
)
from ._loop_tool_registry_common import (
    update_tool_metadata as _update_tool_metadata,
)
from ._loop_tool_registry_optional import register_optional_tools

ToolContextRequest = _ToolContextRequest


def register_tool(*args: object) -> None:
    _register_tool(*args)


def update_tool_metadata(*args: object, **kwargs: object) -> None:
    _update_tool_metadata(*args, **kwargs)


def set_tool_context(*args: object) -> None:
    _set_tool_context(*args)


def register_default_tools_with_optionals(loop: object) -> None:
    _register_default_tools(loop)
    allowed_dir = loop.workspace if loop.restrict_to_workspace else None
    register_optional_tools(loop, allowed_dir)
