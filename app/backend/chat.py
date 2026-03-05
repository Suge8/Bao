"""ChatMessageModel — QAbstractListModel for chat messages.

Roles: id, role, content, format, status, createdAt
Status values: "typing" | "done" | "error"
Format values: "markdown" | "plain"
"""

from __future__ import annotations

import time
from enum import IntEnum
from typing import Any

from PySide6.QtCore import (
    QAbstractListModel,
    QByteArray,
    QModelIndex,
    QPersistentModelIndex,
    Qt,
)


class _Role(IntEnum):
    _BASE = int(Qt.ItemDataRole.UserRole)
    Id = _BASE + 1
    Role = _BASE + 2
    Content = _BASE + 3
    Format = _BASE + 4
    Status = _BASE + 5
    CreatedAt = _BASE + 6
    EntranceStyle = _BASE + 7
    EntrancePending = _BASE + 8
    EntranceConsumed = _BASE + 9


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
        _Role.EntranceStyle: b"entranceStyle",
        _Role.EntrancePending: b"entrancePending",
        _Role.EntranceConsumed: b"entranceConsumed",
    }

    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        self._messages: list[dict[str, Any]] = []
        self._next_id = 1

    # ------------------------------------------------------------------
    # QAbstractListModel interface
    # ------------------------------------------------------------------

    def rowCount(
        self,
        parent: QModelIndex | QPersistentModelIndex = QModelIndex(),  # noqa: B008
    ) -> int:
        return len(self._messages)

    def data(
        self,
        index: QModelIndex | QPersistentModelIndex,
        role: int = int(Qt.ItemDataRole.DisplayRole),
    ) -> Any:
        if not index.isValid() or not (0 <= index.row() < len(self._messages)):
            return None
        msg = self._messages[index.row()]
        try:
            r = _Role(role)
        except ValueError:
            return None
        return msg.get(r.name.lower())

    def roleNames(self) -> dict[int, QByteArray]:
        return {int(k): QByteArray(v) for k, v in self._ROLE_NAMES.items()}

    # ------------------------------------------------------------------
    # Mutation API
    # ------------------------------------------------------------------

    def append_user(self, text: str) -> int:
        """Append a user message; return its row index."""
        return self._append({"role": "user", "content": text, "format": "plain", "status": "done"})

    def append_assistant(
        self,
        text: str = "",
        status: str = "typing",
        entrance_style: str = "assistantReceived",
        entrance_pending: bool = True,
    ) -> int:
        """Append an assistant message placeholder; return its row index."""
        return self._append(
            {
                "role": "assistant",
                "content": text,
                "format": "markdown",
                "status": status,
                "entranceStyle": entrance_style,
                "entrancePending": entrance_pending,
                "entranceConsumed": not entrance_pending,
            }
        )

    def append_system(
        self,
        text: str,
        status: str = "done",
        *,
        entrance_style: str = "system",
        entrance_pending: bool = True,
    ) -> int:
        """Append a system message (gateway status, errors, etc.); return row index."""
        return self._append(
            {
                "role": "system",
                "content": text,
                "format": "plain",
                "status": status,
                "entranceStyle": entrance_style,
                "entrancePending": entrance_pending,
                "entranceConsumed": not entrance_pending,
            }
        )

    def consumeEntrance(self, row: int) -> None:
        if not (0 <= row < len(self._messages)):
            return
        msg = self._messages[row]
        if msg.get("entranceconsumed") is True and msg.get("entrancepending") is False:
            return
        msg["entrancepending"] = False
        msg["entranceconsumed"] = True
        idx = self.index(row)
        self.dataChanged.emit(idx, idx, [int(_Role.EntrancePending), int(_Role.EntranceConsumed)])

    def consumeEntranceById(self, message_id: int) -> None:
        row = self._row_by_message_id(message_id)
        if row < 0:
            return
        self.consumeEntrance(row)

    def mark_entrance_pending(self, row: int) -> None:
        if not (0 <= row < len(self._messages)):
            return
        msg = self._messages[row]
        if msg.get("entrancepending") is True and msg.get("entranceconsumed") is False:
            return
        msg["entrancepending"] = True
        msg["entranceconsumed"] = False
        idx = self.index(row)
        self.dataChanged.emit(idx, idx, [int(_Role.EntrancePending), int(_Role.EntranceConsumed)])

    def mark_entrance_pending_by_id(self, message_id: int) -> None:
        row = self._row_by_message_id(message_id)
        if row < 0:
            return
        self.mark_entrance_pending(row)

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

    def set_format(self, row: int, fmt: str) -> None:
        if not (0 <= row < len(self._messages)):
            return
        self._messages[row]["format"] = fmt
        idx = self.index(row)
        self.dataChanged.emit(idx, idx, [int(_Role.Format)])

    def clear(self) -> None:
        """Remove all messages without emitting reset (uses removeRows)."""
        if not self._messages:
            return
        self.beginRemoveRows(QModelIndex(), 0, len(self._messages) - 1)
        self._messages.clear()
        self.endRemoveRows()

    @staticmethod
    def _normalize_status(status: Any, default: str = "done") -> str:
        if isinstance(status, str) and status in {"typing", "done", "error"}:
            return status
        return default

    @staticmethod
    def prepare_history(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        prepared: list[dict[str, Any]] = []
        for i, m in enumerate(messages):
            role = m.get("role", "user")
            content = m.get("content", "")
            status = ChatMessageModel._normalize_status(m.get("status"), default="done")
            if role == "assistant":
                prepared.append(
                    {
                        "id": i + 1,
                        "createdat": 0,
                        "role": "assistant",
                        "content": content,
                        "format": "plain",
                        "status": status,
                        "entrancestyle": "none",
                        "entrancepending": False,
                        "entranceconsumed": True,
                    }
                )
            elif role == "system":
                prepared.append(
                    {
                        "id": i + 1,
                        "createdat": 0,
                        "role": "system",
                        "content": content,
                        "format": "plain",
                        "status": status,
                        "entrancestyle": "none",
                        "entrancepending": False,
                        "entranceconsumed": True,
                    }
                )
            elif role == "user":
                if m.get("_source"):
                    prepared.append(
                        {
                            "id": i + 1,
                            "createdat": 0,
                            "role": "system",
                            "content": content,
                            "format": "plain",
                            "status": status,
                            "entrancestyle": "none",
                            "entrancepending": False,
                            "entranceconsumed": True,
                        }
                    )
                else:
                    prepared.append(
                        {
                            "id": i + 1,
                            "createdat": 0,
                            "role": "user",
                            "content": content,
                            "format": "plain",
                            "status": status,
                            "entrancestyle": "none",
                            "entrancepending": False,
                            "entranceconsumed": True,
                        }
                    )
            elif role in ("tool", "tool_calls"):
                label = "\U0001f527 " + (content if isinstance(content, str) else str(content))
                prepared.append(
                    {
                        "id": i + 1,
                        "createdat": 0,
                        "role": "system",
                        "content": label,
                        "format": "plain",
                        "status": status,
                        "entrancestyle": "none",
                        "entrancepending": False,
                        "entranceconsumed": True,
                    }
                )
        return prepared

    def load_prepared(self, prepared_messages: list[dict[str, Any]]) -> None:
        if self._is_render_equivalent(prepared_messages):
            return
        if self._can_append_without_reset(prepared_messages):
            append_from = len(self._messages)
            self.beginInsertRows(QModelIndex(), append_from, len(prepared_messages) - 1)
            self._messages = prepared_messages
            self._next_id = len(prepared_messages) + 1
            self.endInsertRows()
            return
        if self._can_prepend_without_reset(prepared_messages):
            prepend_count = len(prepared_messages) - len(self._messages)
            self.beginInsertRows(QModelIndex(), 0, prepend_count - 1)
            self._messages = prepared_messages
            self._next_id = len(prepared_messages) + 1
            self.endInsertRows()
            return
        self.beginResetModel()
        self._messages = prepared_messages
        self._next_id = len(prepared_messages) + 1
        self.endResetModel()

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
        msg.setdefault("entrancestyle", "none")
        msg.setdefault("entrancepending", False)
        msg.setdefault("entranceconsumed", True)
        self._next_id += 1
        self.beginInsertRows(QModelIndex(), row, row)
        self._messages.append(msg)
        self.endInsertRows()
        return row

    def _row_by_message_id(self, message_id: int) -> int:
        for i, msg in enumerate(self._messages):
            if msg.get("id") == message_id:
                return i
        return -1

    def remove_row(self, row: int) -> None:
        if not (0 <= row < len(self._messages)):
            return
        self.beginRemoveRows(QModelIndex(), row, row)
        del self._messages[row]
        self.endRemoveRows()

    def _is_render_equivalent(self, prepared_messages: list[dict[str, Any]]) -> bool:
        if len(prepared_messages) != len(self._messages):
            return False
        for left, right in zip(self._messages, prepared_messages):
            if self._render_tuple(left) != self._render_tuple(right):
                return False
        return True

    def _can_prepend_without_reset(self, prepared_messages: list[dict[str, Any]]) -> bool:
        if not self._messages:
            return False
        if len(prepared_messages) <= len(self._messages):
            return False
        tail = prepared_messages[-len(self._messages) :]
        for left, right in zip(self._messages, tail):
            if self._render_tuple(left) != self._render_tuple(right):
                return False
        return True

    def _can_append_without_reset(self, prepared_messages: list[dict[str, Any]]) -> bool:
        if not self._messages:
            return False
        if len(prepared_messages) <= len(self._messages):
            return False
        head = prepared_messages[: len(self._messages)]
        for left, right in zip(self._messages, head):
            if self._render_tuple(left) != self._render_tuple(right):
                return False
        return True

    @staticmethod
    def _render_tuple(message: dict[str, Any]) -> tuple[str, str, str, str]:
        role = message.get("role", "")
        content = message.get("content", "")
        fmt = message.get("format", "")
        status = message.get("status", "")
        role_s = role if isinstance(role, str) else str(role)
        fmt_s = fmt if isinstance(fmt, str) else str(fmt)
        if role_s == "assistant" and fmt_s in ("plain", "markdown"):
            fmt_s = "assistant_text"
        return (
            role_s,
            content if isinstance(content, str) else str(content),
            fmt_s,
            status if isinstance(status, str) else str(status),
        )

    def load_history(self, messages: list[dict[str, Any]]) -> None:
        """Replace all messages with session history from SessionManager."""
        self.load_prepared(self.prepare_history(messages))
