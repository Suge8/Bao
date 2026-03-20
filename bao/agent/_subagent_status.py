from __future__ import annotations

from ._subagent_status_runtime import _SubagentStatusRuntimeMixin
from ._subagent_status_spawn import _SubagentStatusSpawnMixin


class SubagentStatusMixin(_SubagentStatusSpawnMixin, _SubagentStatusRuntimeMixin):
    _MAX_COMPLETED: int = 50
    _MAX_RECENT_ACTIONS: int = 6
    _PROGRESS_INTERVAL: int = 5
