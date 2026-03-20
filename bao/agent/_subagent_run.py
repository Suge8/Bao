from __future__ import annotations

from ._subagent_run_actions import _SubagentRunActionsMixin
from ._subagent_run_loop import _SubagentRunLoopMixin
from ._subagent_run_notify import _SubagentRunNotifyMixin


class SubagentRunMixin(
    _SubagentRunLoopMixin,
    _SubagentRunActionsMixin,
    _SubagentRunNotifyMixin,
):
    pass
