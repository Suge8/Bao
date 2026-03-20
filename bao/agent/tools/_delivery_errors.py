from __future__ import annotations

from bao.agent.tool_result import ToolExecutionResult

_SEND_FAILURE_GUARDRAIL = (
    "Do not claim success. Explain the send failure and ask for a corrected target when needed."
)
_SESSION_DISCOVERY_HINT = (
    "If you do not already know the exact target, use session_lookup/session_default/"
    "session_resolve first."
)
_TELEGRAM_TARGET_HINT = (
    "For Telegram, chat_id must be a real Telegram chat identifier from an observed session; "
    "do not use a phone number unless the channel truly uses phone ids."
)


def delivery_error_result(
    *,
    code: str,
    message: str,
    guidance: str = "",
) -> ToolExecutionResult:
    detail = message.strip()
    extra = guidance.strip()
    value = detail
    if extra:
        value = f"{value}\n{extra}"
    value = f"{value}\n\n[{_SEND_FAILURE_GUARDRAIL}]"
    return ToolExecutionResult.error(code=code, message=detail, value=value)


__all__ = [
    "_SESSION_DISCOVERY_HINT",
    "_TELEGRAM_TARGET_HINT",
    "delivery_error_result",
]
