from __future__ import annotations

import re

PLAN_STATE_KEY = "_plan_state"
PLAN_ARCHIVED_KEY = "_plan_archived"
PLAN_SCHEMA_VERSION = 1

PLAN_MAX_STEPS = 10
PLAN_MAX_STEP_CHARS = 200
PLAN_MAX_PROMPT_CHARS = 800
PLAN_MAX_GOAL_CHARS = 100

STATUS_PENDING = "pending"
STATUS_DONE = "done"
STATUS_SKIPPED = "skipped"
STATUS_FAILED = "failed"
STATUS_INTERRUPTED = "interrupted"

PLAN_STATUSES = (
    STATUS_PENDING,
    STATUS_DONE,
    STATUS_SKIPPED,
    STATUS_FAILED,
    STATUS_INTERRUPTED,
)
UPDATEABLE_STATUSES = (STATUS_DONE, STATUS_SKIPPED, STATUS_FAILED, STATUS_INTERRUPTED)

STEP_RE = re.compile(
    r"^\s*(?:\d+\.\s*)?\[(pending|done|skipped|failed|interrupted)\]\s*(.*)$",
    flags=re.IGNORECASE,
)
LEADING_INDEX_RE = re.compile(r"^\s*\d+\.\s*")

MARKDOWN_CHANNELS = frozenset(
    {
        "telegram",
        "discord",
        "slack",
        "feishu",
        "dingtalk",
        "whatsapp",
    }
)
LITE_MARKDOWN_CHANNELS = frozenset({"whatsapp"})
