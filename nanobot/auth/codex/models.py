"""Codex OAuth data models."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CodexToken:
    """Codex OAuth token data structure."""

    access: str
    refresh: str
    expires: int
    account_id: str
