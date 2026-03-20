from __future__ import annotations

from ._subagent_tool_runtime import _SubagentToolRuntimeMixin
from ._subagent_tool_setup import _SubagentToolSetupMixin


class SubagentToolingMixin(_SubagentToolSetupMixin, _SubagentToolRuntimeMixin):
    pass
