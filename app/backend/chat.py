"""ChatMessageModel — QAbstractListModel for chat messages.

Roles: id, role, content, format, status, createdAt
Status values: "typing" | "done" | "error"
Format values: "markdown" | "plain"
"""

from __future__ import annotations

import time
from enum import IntEnum
from typing import Any

from PySide6.QtCore import QAbstractListModel, QModelIndex, Qt


class _Role(IntEnum):
    Id = Qt.UserRole + 1
    Role = Qt.UserRole + 2
    Content = Qt.UserRole + 3
    Format = Qt.UserRole + 4
    Status = Qt.UserRole + 5
    CreatedAt = Qt.UserRole + 6


class ChatMessageModel(QAbstractListModel):
    """Incremental list model for chat messages.

    Never calls beginResetModel — all mutations use beginInsertRows / dataChanged.
    """

    _ROLE_NAMES = {
        _Role.Id: b"id",
        _Role.Role: b"role",
        _Role.Content: b"content",
        _Role.Format: b"format",
        _Role.Status: b"status",
        _Role.CreatedAt: b"createdAt",
    }

    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        self._messages: list[dict[str, Any]] = []
        self._next_id = 1

    # ------------------------------------------------------------------
    # QAbstractListModel interface
    # ------------------------------------------------------------------

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: B008
        return len(self._messages)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole) -> Any:
        if not index.isValid() or not (0 <= index.row() < len(self._messages)):
            return None
        msg = self._messages[index.row()]
        try:
            r = _Role(role)
        except ValueError:
            return None
        return msg.get(r.name.lower())

    def roleNames(self) -> dict[int, bytes]:
        return {int(k): v for k, v in self._ROLE_NAMES.items()}

    # ------------------------------------------------------------------
    # Mutation API
    # ------------------------------------------------------------------

    def append_user(self, text: str) -> int:
        """Append a user message; return its row index."""
        return self._append({"role": "user", "content": text, "format": "plain", "status": "done"})

    def append_assistant(self, text: str = "", status: str = "typing") -> int:
        """Append an assistant message placeholder; return its row index."""
        return self._append(
            {"role": "assistant", "content": text, "format": "markdown", "status": status}
        )

    def append_system(self, text: str, status: str = "done") -> int:
        """Append a system message (gateway status, errors, etc.); return row index."""
        return self._append(
            {"role": "system", "content": text, "format": "plain", "status": status}
        )

    def update_content(self, row: int, new_text: str) -> None:
        """Replace the content of an existing row (incremental typewriter update)."""
        if not (0 <= row < len(self._messages)):
            return
        self._messages[row]["content"] = new_text
        idx = self.index(row)
        self.dataChanged.emit(idx, idx, [int(_Role.Content)])

    def set_status(self, row: int, status: str) -> None:
        """Update the status field of an existing row."""
        if not (0 <= row < len(self._messages)):
            return
        self._messages[row]["status"] = status
        idx = self.index(row)
        self.dataChanged.emit(idx, idx, [int(_Role.Status)])

    def clear(self) -> None:
        """Remove all messages without emitting reset (uses removeRows)."""
        if not self._messages:
            return
        self.beginRemoveRows(QModelIndex(), 0, len(self._messages) - 1)
        self._messages.clear()
        self.endRemoveRows()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _append(self, fields: dict[str, Any]) -> int:
        row = len(self._messages)
        msg = {
            "id": self._next_id,
            "createdat": int(time.time() * 1000),
            **{k.lower(): v for k, v in fields.items()},
        }
        self._next_id += 1
        self.beginInsertRows(QModelIndex(), row, row)
        self._messages.append(msg)
        self.endInsertRows()
        return row
    def load_history(self, messages: list[dict[str, Any]]) -> None:
        """Replace all messages with session history from SessionManager."""
        self.clear()
        for m in messages:
            role = m.get("role", "user")
            content = m.get("content", "")
            if role == "assistant":
                self._append({"role": "assistant", "content": content, "format": "markdown", "status": "done"})
            elif role == "system":
                self._append({"role": "system", "content": content, "format": "plain", "status": "done"})
            elif role == "user":
                self._append({"role": "user", "content": content, "format": "plain", "status": "done"})
