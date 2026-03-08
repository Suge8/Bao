"""ChatMessageModel — QAbstractListModel for chat messages.

Roles: id, role, content, format, status, createdAt
Status values: "typing" | "done" | "error"
Format values: "markdown" | "plain"
"""

from __future__ import annotations

import time
from datetime import datetime
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
    DividerText = _BASE + 9


class ChatMessageModel(QAbstractListModel):
    """Incremental list model for chat messages.

    Prefers incremental updates via beginInsertRows / dataChanged.
    Falls back to beginResetModel when history cannot be merged safely.
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
        _Role.DividerText: b"dividerText",
    }
    _UPDATE_ROLES = [int(role) for role in _ROLE_NAMES]

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
        return self._append(
            {
                "role": "user",
                "content": text,
                "format": "plain",
                "status": "done",
                "entranceStyle": "userSent",
                "entrancePending": True,
            }
        )

    def append_assistant(
        self,
        text: str = "",
        status: str = "typing",
        entrance_style: str = "assistantReceived",
        entrance_pending: bool = True,
    ) -> int:
        """Append an assistant message placeholder; return its row index."""
        entrance_style = self._normalize_entrance_style(entrance_style, default="assistantReceived")
        return self._append(
            {
                "role": "assistant",
                "content": text,
                "format": "markdown",
                "status": status,
                "entranceStyle": entrance_style,
                "entrancePending": entrance_pending,
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
        entrance_style = self._normalize_entrance_style(entrance_style, default="system")
        return self._append(
            {
                "role": "system",
                "content": text,
                "format": "plain",
                "status": status,
                "entranceStyle": entrance_style,
                "entrancePending": entrance_pending,
            }
        )

    def consumeEntrance(self, row: int) -> None:
        if not (0 <= row < len(self._messages)):
            return
        msg = self._messages[row]
        if msg.get("entrancepending") is False:
            return
        msg["entrancepending"] = False
        idx = self.index(row)
        self.dataChanged.emit(idx, idx, [int(_Role.EntrancePending)])

    def consumeEntranceById(self, message_id: int) -> None:
        row = self._row_by_message_id(message_id)
        if row < 0:
            return
        self.consumeEntrance(row)

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
    def _normalize_entrance_style(style: Any, default: str = "none") -> str:
        if isinstance(style, str) and style in {
            "none",
            "assistantReceived",
            "userSent",
            "system",
            "greeting",
        }:
            return style
        return default

    @staticmethod
    def _normalize_format(fmt: Any, default: str = "plain") -> str:
        if isinstance(fmt, str) and fmt in {"plain", "markdown"}:
            return fmt
        return default

    @staticmethod
    def _build_prepared_message(
        index: int,
        *,
        role: str,
        content: Any,
        status: str,
        entrance_style: str = "none",
        fmt: str = "plain",
        created_at: int = 0,
        source: str | None = None,
    ) -> dict[str, Any]:
        prepared = {
            "id": index + 1,
            "createdat": created_at,
            "role": role,
            "content": content,
            "format": fmt,
            "status": status,
            "entrancestyle": entrance_style,
            "entrancepending": False,
            "dividertext": "",
        }
        if isinstance(source, str) and source:
            prepared["_source"] = source
        return prepared

    @staticmethod
    def _normalize_created_at(value: Any) -> int:
        if isinstance(value, (int, float)):
            return max(0, int(value))
        if isinstance(value, str):
            raw = value.strip()
            if not raw:
                return 0
            if raw.isdigit():
                return max(0, int(raw))
            try:
                dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            except ValueError:
                return 0
            return max(0, int(dt.timestamp() * 1000))
        return 0

    @classmethod
    def _message_created_at(cls, message: dict[str, Any]) -> int:
        for key in ("created_at", "createdAt", "createdat", "timestamp"):
            if key in message:
                return cls._normalize_created_at(message.get(key))
        return 0

    @staticmethod
    def _same_calendar_day(left_ms: int, right_ms: int) -> bool:
        left = datetime.fromtimestamp(left_ms / 1000)
        right = datetime.fromtimestamp(right_ms / 1000)
        return left.date() == right.date()

    @staticmethod
    def _format_day_divider(timestamp_ms: int) -> str:
        dt = datetime.fromtimestamp(timestamp_ms / 1000)
        now = datetime.now()
        if dt.year == now.year:
            return f"{dt.month}/{dt.day}"
        return f"{dt.year}/{dt.month}/{dt.day}"

    @staticmethod
    def _format_gap_divider(timestamp_ms: int) -> str:
        dt = datetime.fromtimestamp(timestamp_ms / 1000)
        return dt.strftime("%H:%M")

    @classmethod
    def _divider_text_for(
        cls,
        current_created_at: int,
        previous_created_at: int,
    ) -> str:
        if current_created_at <= 0:
            return ""
        if previous_created_at <= 0:
            return ""
        if not cls._same_calendar_day(previous_created_at, current_created_at):
            return cls._format_day_divider(current_created_at)
        if current_created_at - previous_created_at >= 6 * 60 * 60 * 1000:
            now_ms = int(datetime.now().timestamp() * 1000)
            if cls._same_calendar_day(current_created_at, now_ms):
                return cls._format_gap_divider(current_created_at)
            return cls._format_day_divider(current_created_at)
        return ""

    @classmethod
    def _apply_divider_texts(cls, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        previous_created_at = 0
        for index, message in enumerate(messages):
            current_created_at = cls._normalize_created_at(message.get("createdat", 0))
            message["dividertext"] = cls._divider_text_for(
                current_created_at,
                previous_created_at,
            )
            previous_created_at = current_created_at
        return messages

    @staticmethod
    def prepare_history(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        prepared: list[dict[str, Any]] = []
        for i, m in enumerate(messages):
            role = m.get("role", "user")
            content = m.get("content", "")
            status = ChatMessageModel._normalize_status(m.get("status"), default="done")
            fmt_default = "markdown" if role == "assistant" else "plain"
            fmt = ChatMessageModel._normalize_format(m.get("format"), default=fmt_default)
            created_at = ChatMessageModel._message_created_at(m)

            if role == "assistant":
                prepared.append(
                    ChatMessageModel._build_prepared_message(
                        i,
                        role="assistant",
                        content=content,
                        status=status,
                        fmt=fmt,
                        created_at=created_at,
                        source=m.get("_source"),
                    )
                )
            elif role == "system":
                entrance_style = ChatMessageModel._normalize_entrance_style(
                    m.get("entrance_style"), default="none"
                )
                prepared.append(
                    ChatMessageModel._build_prepared_message(
                        i,
                        role="system",
                        content=content,
                        status=status,
                        entrance_style=entrance_style,
                        fmt=fmt,
                        created_at=created_at,
                        source=m.get("_source"),
                    )
                )
            elif role == "user":
                if m.get("_source"):
                    entrance_style = ChatMessageModel._normalize_entrance_style(
                        m.get("entrance_style"), default="none"
                    )
                    prepared.append(
                        ChatMessageModel._build_prepared_message(
                            i,
                            role="system",
                            content=content,
                            status=status,
                            entrance_style=entrance_style,
                            fmt=fmt,
                            created_at=created_at,
                            source=m.get("_source"),
                        )
                    )
                else:
                    prepared.append(
                        ChatMessageModel._build_prepared_message(
                            i,
                            role="user",
                            content=content,
                            status=status,
                            fmt=fmt,
                            created_at=created_at,
                        )
                    )
            elif role in ("tool", "tool_calls"):
                label = "\U0001f527 " + (content if isinstance(content, str) else str(content))
                entrance_style = ChatMessageModel._normalize_entrance_style(
                    m.get("entrance_style"), default="none"
                )
                prepared.append(
                    ChatMessageModel._build_prepared_message(
                        i,
                        role="system",
                        content=label,
                        status=status,
                        entrance_style=entrance_style,
                        fmt=fmt,
                        created_at=created_at,
                    )
                )
        return ChatMessageModel._apply_divider_texts(prepared)

    def load_prepared(
        self, prepared_messages: list[dict[str, Any]], *, preserve_transient_tail: bool = False
    ) -> None:
        next_messages = self._messages_for_prepared_load(
            prepared_messages, preserve_transient_tail=preserve_transient_tail
        )
        if self._is_render_equivalent(next_messages):
            return
        if self._can_update_without_reset(next_messages):
            self._update_without_reset(next_messages)
            return
        if self._can_reconcile_transient_tail_without_reset(next_messages):
            self._reconcile_transient_tail_without_reset(next_messages)
            return
        if self._can_append_without_reset(next_messages):
            append_from = len(self._messages)
            self.beginInsertRows(QModelIndex(), append_from, len(next_messages) - 1)
            self._messages = next_messages
            self._next_id = len(next_messages) + 1
            self.endInsertRows()
            return
        if self._can_prepend_without_reset(next_messages):
            prepend_count = len(next_messages) - len(self._messages)
            self.beginInsertRows(QModelIndex(), 0, prepend_count - 1)
            self._messages = next_messages
            self._next_id = len(next_messages) + 1
            self.endInsertRows()
            return
        self.beginResetModel()
        self._messages = next_messages
        self._next_id = len(next_messages) + 1
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
        previous_created_at = 0
        if self._messages:
            previous_created_at = self._normalize_created_at(self._messages[-1].get("createdat", 0))
        msg["dividertext"] = self._divider_text_for(
            self._normalize_created_at(msg.get("createdat", 0)),
            previous_created_at,
        )
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

    def message_at(self, row: int) -> dict[str, Any] | None:
        if not (0 <= row < len(self._messages)):
            return None
        return self._messages[row]

    def _is_render_equivalent(self, prepared_messages: list[dict[str, Any]]) -> bool:
        if len(prepared_messages) != len(self._messages):
            return False
        return self._render_sequences_match(self._messages, prepared_messages)

    def _can_prepend_without_reset(self, prepared_messages: list[dict[str, Any]]) -> bool:
        if not self._messages:
            return False
        if len(prepared_messages) <= len(self._messages):
            return False
        tail = prepared_messages[-len(self._messages) :]
        return self._render_sequences_match(self._messages, tail)

    def _can_update_without_reset(self, prepared_messages: list[dict[str, Any]]) -> bool:
        if len(prepared_messages) != len(self._messages):
            return False
        for current, prepared in zip(self._messages, prepared_messages):
            current_role = current.get("role")
            if current_role != prepared.get("role"):
                return False
            if current_role == "system":
                current_pending = bool(current.get("entrancepending"))
                prepared_pending = bool(prepared.get("entrancepending"))
                if (
                    not current_pending
                    and not prepared_pending
                    and current.get("entrancestyle", "none")
                    != prepared.get("entrancestyle", "none")
                ):
                    return False
        return True

    def _update_without_reset(self, prepared_messages: list[dict[str, Any]]) -> None:
        for row, prepared in enumerate(prepared_messages):
            self._replace_row_without_reset(row, prepared)

    def _can_append_without_reset(self, prepared_messages: list[dict[str, Any]]) -> bool:
        if not self._messages:
            return False
        if len(prepared_messages) <= len(self._messages):
            return False
        head = prepared_messages[: len(self._messages)]
        return self._render_sequences_match(self._messages, head)

    def _can_reconcile_transient_tail_without_reset(
        self, prepared_messages: list[dict[str, Any]]
    ) -> bool:
        assistant_tail = self._trailing_assistant_block()
        if not assistant_tail:
            return False

        stable_prefix_count = len(self._messages) - len(assistant_tail)
        if len(prepared_messages) < stable_prefix_count:
            return False
        stable_prefix = self._messages[:stable_prefix_count]
        if not self._render_sequences_match(stable_prefix, prepared_messages[:stable_prefix_count]):
            return False

        remainder = prepared_messages[stable_prefix_count:]
        split = 0
        while split < len(remainder) and remainder[split].get("role") == "system":
            split += 1
        next_tail = remainder[split:]
        return all(msg.get("role") == "assistant" for msg in next_tail)

    def _reconcile_transient_tail_without_reset(
        self, prepared_messages: list[dict[str, Any]]
    ) -> None:
        assistant_tail = self._trailing_assistant_block()
        stable_prefix_count = len(self._messages) - len(assistant_tail)
        remainder = prepared_messages[stable_prefix_count:]
        split = 0
        while split < len(remainder) and remainder[split].get("role") == "system":
            split += 1
        inserted_rows = remainder[:split]
        next_tail = remainder[split:]

        if inserted_rows:
            self.beginInsertRows(
                QModelIndex(), stable_prefix_count, stable_prefix_count + split - 1
            )
            self._messages[stable_prefix_count:stable_prefix_count] = [
                dict(msg) for msg in inserted_rows
            ]
            self.endInsertRows()

        tail_start = stable_prefix_count + split
        common_tail_count = min(len(assistant_tail), len(next_tail))
        for offset in range(common_tail_count):
            self._replace_row_without_reset(tail_start + offset, next_tail[offset])

        if len(next_tail) < len(assistant_tail):
            remove_start = tail_start + len(next_tail)
            remove_end = tail_start + len(assistant_tail) - 1
            self.beginRemoveRows(QModelIndex(), remove_start, remove_end)
            del self._messages[remove_start : remove_end + 1]
            self.endRemoveRows()
        elif len(next_tail) > len(assistant_tail):
            insert_start = tail_start + len(assistant_tail)
            insert_rows = next_tail[len(assistant_tail) :]
            self.beginInsertRows(QModelIndex(), insert_start, insert_start + len(insert_rows) - 1)
            self._messages[insert_start:insert_start] = [dict(msg) for msg in insert_rows]
            self.endInsertRows()

        self._next_id = len(prepared_messages) + 1

    def _replace_row_without_reset(self, row: int, prepared: dict[str, Any]) -> None:
        current = self._messages[row]
        if self._render_tuple(current) == self._render_tuple(prepared):
            return
        self._messages[row] = {
            **current,
            **prepared,
            "id": current.get("id", prepared.get("id", row + 1)),
            "createdat": current.get("createdat", prepared.get("createdat", 0)),
        }
        idx = self.index(row)
        self.dataChanged.emit(idx, idx, self._UPDATE_ROLES)

    def _messages_for_prepared_load(
        self, prepared_messages: list[dict[str, Any]], *, preserve_transient_tail: bool
    ) -> list[dict[str, Any]]:
        if not preserve_transient_tail:
            return self._apply_divider_texts(prepared_messages)
        return self._apply_divider_texts(self._merge_transient_assistant_tail(prepared_messages))

    def _merge_transient_assistant_tail(
        self, prepared_messages: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        transient_tail = self._trailing_transient_assistant_tail()
        if not transient_tail:
            return prepared_messages

        stable_prefix_count = len(self._messages) - len(transient_tail)
        if len(prepared_messages) < stable_prefix_count:
            return prepared_messages

        stable_prefix = self._messages[:stable_prefix_count]
        prepared_prefix = prepared_messages[:stable_prefix_count]
        if not self._render_sequences_match(stable_prefix, prepared_prefix):
            return prepared_messages

        remaining_tail = self._remaining_transient_tail(
            prepared_messages[stable_prefix_count:], transient_tail
        )
        if remaining_tail is None:
            return prepared_messages

        return prepared_messages + remaining_tail

    def _trailing_transient_assistant_tail(self) -> list[dict[str, Any]]:
        assistant_tail = self._trailing_assistant_block()
        if not assistant_tail or assistant_tail[-1].get("status") != "typing":
            return []
        return assistant_tail

    def _trailing_assistant_block(self) -> list[dict[str, Any]]:
        if not self._messages:
            return []
        if self._messages[-1].get("role") != "assistant":
            return []

        tail_start = len(self._messages) - 1
        while tail_start > 0 and self._messages[tail_start - 1].get("role") == "assistant":
            tail_start -= 1
        return self._messages[tail_start:]

    def _remaining_transient_tail(
        self, prepared_remainder: list[dict[str, Any]], transient_tail: list[dict[str, Any]]
    ) -> list[dict[str, Any]] | None:
        for inserted_count in range(len(prepared_remainder) + 1):
            inserted_rows = prepared_remainder[:inserted_count]
            tail_prefix = prepared_remainder[inserted_count:]
            if any(msg.get("role") != "system" for msg in inserted_rows):
                continue
            if len(tail_prefix) > len(transient_tail):
                continue
            if not self._render_sequences_match(transient_tail[: len(tail_prefix)], tail_prefix):
                continue
            return [dict(msg) for msg in transient_tail[len(tail_prefix) :]]
        return None

    @classmethod
    def _render_sequences_match(
        cls, left_messages: list[dict[str, Any]], right_messages: list[dict[str, Any]]
    ) -> bool:
        if len(left_messages) != len(right_messages):
            return False
        for left, right in zip(left_messages, right_messages):
            if cls._render_tuple(left) != cls._render_tuple(right):
                return False
        return True

    @staticmethod
    def _render_tuple(message: dict[str, Any]) -> tuple[str, str, str, str, str, str]:
        role = message.get("role", "")
        content = message.get("content", "")
        fmt = message.get("format", "")
        status = message.get("status", "")
        entrance_style = message.get("entrancestyle", "none")
        divider_text = message.get("dividertext", "")
        role_s = role if isinstance(role, str) else str(role)
        fmt_s = fmt if isinstance(fmt, str) else str(fmt)
        entrance_s = ""
        if role_s == "system":
            entrance_s = entrance_style if isinstance(entrance_style, str) else str(entrance_style)
        return (
            role_s,
            content if isinstance(content, str) else str(content),
            fmt_s,
            status if isinstance(status, str) else str(status),
            entrance_s,
            divider_text if isinstance(divider_text, str) else str(divider_text),
        )

    def load_history(self, messages: list[dict[str, Any]]) -> None:
        """Replace all messages with session history from SessionManager."""
        self.load_prepared(self.prepare_history(messages))
