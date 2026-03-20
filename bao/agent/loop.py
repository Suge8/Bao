"""Agent loop: the core processing engine."""

from __future__ import annotations

from bao.agent._loop_agent_support_mixin import LoopAgentSupportMixin
from bao.agent._loop_background_mixin import LoopBackgroundMixin
from bao.agent._loop_dispatch_mixin import LoopDispatchMixin
from bao.agent._loop_init_mixin import LoopInitMixin
from bao.agent._loop_language_mixin import LoopLanguageMixin
from bao.agent._loop_route_text_mixin import LoopRouteTextMixin
from bao.agent._loop_routing_mixin import LoopRoutingMixin
from bao.agent._loop_run_loop_mixin import LoopRunLoopMixin
from bao.agent._loop_session_context_mixin import LoopSessionContextMixin
from bao.agent._loop_tool_facade_mixin import LoopToolFacadeMixin
from bao.agent._loop_tool_hint_mixin import LoopToolHintMixin
from bao.agent._loop_tool_iteration_mixin import LoopToolIterationMixin
from bao.agent._loop_tool_runtime_mixin import LoopToolRuntimeMixin
from bao.agent._loop_turn_output_mixin import LoopTurnOutputMixin
from bao.agent._loop_types import ToolObservabilityCounters as _LoopToolObservabilityCounters
from bao.agent._loop_types import archive_all_signature as _loop_archive_all_signature
from bao.agent._loop_user_message_flow_mixin import LoopUserMessageFlowMixin
from bao.agent._loop_user_message_setup_mixin import LoopUserMessageSetupMixin
from bao.agent.subagent import SubagentManager as _LoopSubagentManager

_ToolObservabilityCounters = _LoopToolObservabilityCounters
_archive_all_signature = _loop_archive_all_signature
SubagentManager = _LoopSubagentManager


class AgentLoop(
    LoopInitMixin,
    LoopLanguageMixin,
    LoopRouteTextMixin,
    LoopRoutingMixin,
    LoopToolRuntimeMixin,
    LoopToolIterationMixin,
    LoopRunLoopMixin,
    LoopDispatchMixin,
    LoopToolFacadeMixin,
    LoopSessionContextMixin,
    LoopTurnOutputMixin,
    LoopBackgroundMixin,
    LoopAgentSupportMixin,
    LoopUserMessageSetupMixin,
    LoopUserMessageFlowMixin,
    LoopToolHintMixin,
):
    """Thin facade that composes the agent loop behavior from focused mixins."""
