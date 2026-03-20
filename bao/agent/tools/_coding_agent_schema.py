from __future__ import annotations

from typing import Any

DEFAULT_MODEL_OVERRIDE_DESCRIPTION = (
    "Optional explicit model override. Omit it to use the backend or CLI default model."
)

_COMMON_PROPERTIES: dict[str, dict[str, Any]] = {
    "prompt": {"type": "string", "minLength": 1},
    "project_path": {
        "type": "string",
        "description": "Optional project directory (defaults to workspace)",
    },
    "continue_session": {
        "type": "boolean",
        "description": "Continue previous chat-specific session when available",
    },
    "model": {"type": "string", "description": DEFAULT_MODEL_OVERRIDE_DESCRIPTION},
    "timeout_seconds": {
        "type": "integer",
        "minimum": 30,
        "maximum": 1800,
        "description": "Execution timeout in seconds (default 1800)",
    },
    "response_format": {
        "type": "string",
        "enum": ["hybrid", "json", "text"],
        "description": "Return format: hybrid (default), json, or text",
    },
    "max_retries": {
        "type": "integer",
        "minimum": 0,
        "maximum": 2,
        "description": "Reserved compatibility field; hidden automatic retries are disabled",
    },
    "max_output_chars": {
        "type": "integer",
        "minimum": 200,
        "maximum": 50000,
        "description": "Max chars for stdout/stderr in tool output (default 4000)",
    },
    "include_details": {
        "type": "boolean",
        "description": "Include full tool stdout/stderr in output (default false)",
    },
}


def build_coding_agent_parameters(
    *,
    prompt_description: str,
    session_description: str,
    model_description: str | None = None,
    extra_properties: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    properties = {
        "prompt": {
            **_COMMON_PROPERTIES["prompt"],
            "description": prompt_description,
        },
        "project_path": dict(_COMMON_PROPERTIES["project_path"]),
        "session_id": {
            "type": "string",
            "description": session_description,
        },
        "continue_session": dict(_COMMON_PROPERTIES["continue_session"]),
        "model": {
            **_COMMON_PROPERTIES["model"],
            "description": model_description or _COMMON_PROPERTIES["model"]["description"],
        },
    }
    if extra_properties:
        properties.update(extra_properties)
    properties.update(
        {
            "timeout_seconds": dict(_COMMON_PROPERTIES["timeout_seconds"]),
            "response_format": dict(_COMMON_PROPERTIES["response_format"]),
            "max_retries": dict(_COMMON_PROPERTIES["max_retries"]),
            "max_output_chars": dict(_COMMON_PROPERTIES["max_output_chars"]),
            "include_details": dict(_COMMON_PROPERTIES["include_details"]),
        }
    )
    return {
        "type": "object",
        "properties": properties,
        "required": ["prompt"],
    }
