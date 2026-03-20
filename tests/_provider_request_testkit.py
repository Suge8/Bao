from __future__ import annotations

from typing import Any


def request_messages(request: Any) -> list[dict[str, Any]]:
    return request.messages if hasattr(request, "messages") else request


def request_tools(request: Any) -> list[dict[str, Any]] | None:
    return request.tools if hasattr(request, "tools") else None
