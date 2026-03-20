from __future__ import annotations

import json
import time
from typing import Any

from ._task_status_format import task_to_snapshot


def invalid_schema_payload(raw_schema_version: Any) -> str:
    return json.dumps(
        {
            "schema_version": 1,
            "error": {
                "code": "invalid_schema_version",
                "message": (
                    "schema_version must be an integer-compatible value "
                    f"(got {raw_schema_version!r})."
                ),
            },
        }
    )


def unsupported_schema_payload(schema_version: int) -> str:
    return json.dumps(
        {
            "schema_version": 1,
            "error": {
                "code": "unsupported_schema_version",
                "message": f"Unsupported schema_version: {schema_version}. Only 1 is supported.",
            },
        }
    )


def invalid_task_id_payload() -> str:
    return json.dumps(
        {
            "schema_version": 1,
            "error": {
                "code": "invalid_task_id",
                "message": "task_id must be a non-empty string.",
            },
        }
    )


def task_not_found_payload(task_id: str) -> str:
    return json.dumps(
        {
            "schema_version": 1,
            "error": {
                "code": "task_not_found",
                "message": f"No task found with id '{task_id}'.",
            },
        }
    )


def validate_schema_version(raw_schema_version: Any) -> tuple[int | None, str | None]:
    try:
        schema_version = int(raw_schema_version)
    except (TypeError, ValueError):
        return None, invalid_schema_payload(raw_schema_version)
    if schema_version != 1:
        return None, unsupported_schema_payload(schema_version)
    return schema_version, None


def normalize_task_id(raw_task_id: Any) -> tuple[str | None, str | None]:
    if raw_task_id is None:
        return None, None
    task_id = str(raw_task_id).strip()
    if not task_id:
        return None, invalid_task_id_payload()
    return task_id, None


def build_snapshot_payload(tasks: list[Any]) -> str:
    return json.dumps(
        {
            "schema_version": 1,
            "generated_at": time.time(),
            "tasks": [task_to_snapshot(task) for task in tasks],
        }
    )
