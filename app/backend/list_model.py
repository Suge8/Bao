from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import QAbstractListModel, QByteArray, QModelIndex, Qt


@dataclass(frozen=True)
class SelectionProjection:
    items: list[dict[str, Any]]
    selected_id: str
    selected_item: dict[str, Any]


def build_selection_projection(
    items: list[dict[str, Any]],
    *,
    key_field: str = "id",
    preferred_id: str = "",
) -> SelectionProjection:
    normalized_items = [dict(item) for item in items if isinstance(item, dict)]
    selected_item = next(
        (dict(item) for item in normalized_items if str(item.get(key_field, "")) == preferred_id),
        {},
    )
    selected_id = preferred_id if selected_item else ""
    if not selected_item and normalized_items:
        selected_item = dict(normalized_items[0])
        selected_id = str(selected_item.get(key_field, "") or "")
    return SelectionProjection(
        items=normalized_items,
        selected_id=selected_id,
        selected_item=selected_item,
    )


class KeyValueListModel(QAbstractListModel):
    _MODEL_DATA_ROLE = int(Qt.ItemDataRole.UserRole) + 1

    def __init__(self, parent: Any = None, *, key_field: str = "id") -> None:
        super().__init__(parent)
        self._items: list[dict[str, Any]] = []
        self._key_field = key_field

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: B008
        if parent.isValid():
            return 0
        return len(self._items)

    def data(self, index: QModelIndex, role: int = int(Qt.ItemDataRole.DisplayRole)) -> Any:
        if not index.isValid() or not (0 <= index.row() < len(self._items)):
            return None
        if role == self._MODEL_DATA_ROLE:
            return dict(self._items[index.row()])
        return None

    def roleNames(self) -> dict[int, QByteArray]:
        return {self._MODEL_DATA_ROLE: QByteArray(b"modelData")}

    def replace_items(self, items: list[dict[str, Any]]) -> None:
        self.beginResetModel()
        self._items = [dict(item) for item in items if isinstance(item, dict)]
        self.endResetModel()

    def sync_items(self, items: list[dict[str, Any]]) -> None:
        next_items = [dict(item) for item in items if isinstance(item, dict)]
        next_keys = {self._item_key(item) for item in next_items}
        for remove_index in range(len(self._items) - 1, -1, -1):
            if self._item_key(self._items[remove_index]) in next_keys:
                continue
            self.beginRemoveRows(QModelIndex(), remove_index, remove_index)
            del self._items[remove_index]
            self.endRemoveRows()

        row_index = 0
        while row_index < len(next_items):
            next_item = next_items[row_index]
            next_key = self._item_key(next_item)
            if row_index < len(self._items) and self._item_key(self._items[row_index]) == next_key:
                self._update_item(row_index, next_item)
                row_index += 1
                continue

            found_index = -1
            for search_index in range(row_index + 1, len(self._items)):
                if self._item_key(self._items[search_index]) == next_key:
                    found_index = search_index
                    break
            if found_index >= 0:
                self.beginMoveRows(
                    QModelIndex(),
                    found_index,
                    found_index,
                    QModelIndex(),
                    row_index,
                )
                item = self._items.pop(found_index)
                self._items.insert(row_index, item)
                self.endMoveRows()
            else:
                self.beginInsertRows(QModelIndex(), row_index, row_index)
                self._items.insert(row_index, dict(next_item))
                self.endInsertRows()
            self._update_item(row_index, next_item)
            row_index += 1

    def items(self) -> list[dict[str, Any]]:
        return [dict(item) for item in self._items]

    def item_by_id(self, item_id: str) -> dict[str, Any]:
        target = str(item_id or "")
        if not target:
            return {}
        for item in self._items:
            if self._item_key(item) == target:
                return dict(item)
        return {}

    def _item_key(self, item: dict[str, Any]) -> str:
        return str(item.get(self._key_field, "") or "")

    def _update_item(self, row: int, next_item: dict[str, Any]) -> None:
        current = self._items[row]
        if current == next_item:
            return
        self._items[row] = dict(next_item)
        model_index = self.index(row)
        self.dataChanged.emit(model_index, model_index, [self._MODEL_DATA_ROLE])
