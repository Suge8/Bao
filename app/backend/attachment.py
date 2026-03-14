from __future__ import annotations

from typing import Any

from PySide6.QtCore import (
    Property,
    QAbstractListModel,
    QByteArray,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    Qt,
    Signal,
)

from bao.utils.attachments import build_attachment_payload


class AttachmentDraftModel(QAbstractListModel):
    countChanged = Signal()

    _FILE_NAME_ROLE = int(Qt.ItemDataRole.UserRole) + 1
    _FILE_SIZE_LABEL_ROLE = _FILE_NAME_ROLE + 1
    _FILE_PATH_ROLE = _FILE_NAME_ROLE + 2
    _PREVIEW_URL_ROLE = _FILE_NAME_ROLE + 3
    _IS_IMAGE_ROLE = _FILE_NAME_ROLE + 4
    _EXTENSION_LABEL_ROLE = _FILE_NAME_ROLE + 5

    _ROLE_NAMES = {
        _FILE_NAME_ROLE: b"fileName",
        _FILE_SIZE_LABEL_ROLE: b"fileSizeLabel",
        _FILE_PATH_ROLE: b"filePath",
        _PREVIEW_URL_ROLE: b"previewUrl",
        _IS_IMAGE_ROLE: b"isImage",
        _EXTENSION_LABEL_ROLE: b"extensionLabel",
    }

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._items: list[dict[str, Any]] = []

    @Property(int, notify=countChanged)
    def count(self) -> int:
        return len(self._items)

    def rowCount(
        self,
        parent: QModelIndex | QPersistentModelIndex = QModelIndex(),  # noqa: B008
    ) -> int:
        if parent.isValid():
            return 0
        return len(self._items)

    def data(
        self,
        index: QModelIndex | QPersistentModelIndex,
        role: int = int(Qt.ItemDataRole.DisplayRole),
    ) -> Any:
        if not index.isValid() or not (0 <= index.row() < len(self._items)):
            return None
        item = self._items[index.row()]
        key = self._ROLE_NAMES.get(role)
        if key is None:
            return None
        return item.get(bytes(key).decode())

    def roleNames(self) -> dict[int, QByteArray]:
        return {role: QByteArray(name) for role, name in self._ROLE_NAMES.items()}

    def add_local_paths(self, paths: list[str]) -> bool:
        new_items: list[dict[str, Any]] = []
        existing_paths = {str(item.get("filePath", "")) for item in self._items}
        for raw_path in paths:
            item = build_attachment_payload(raw_path)
            if not isinstance(item, dict):
                continue
            resolved_str = str(item.get("filePath", ""))
            if resolved_str in existing_paths or not resolved_str:
                continue
            new_items.append(item)
            existing_paths.add(resolved_str)
        if not new_items:
            return False
        start = len(self._items)
        end = start + len(new_items) - 1
        self.beginInsertRows(QModelIndex(), start, end)
        self._items.extend(new_items)
        self.endInsertRows()
        self.countChanged.emit()
        return True

    def remove_at(self, index: int) -> bool:
        if not (0 <= index < len(self._items)):
            return False
        self.beginRemoveRows(QModelIndex(), index, index)
        del self._items[index]
        self.endRemoveRows()
        self.countChanged.emit()
        return True

    def clear(self) -> bool:
        if not self._items:
            return False
        self.beginResetModel()
        self._items.clear()
        self.endResetModel()
        self.countChanged.emit()
        return True

    def snapshot_paths(self) -> list[str]:
        return [str(item.get("filePath", "")) for item in self._items if item.get("filePath")]

    def snapshot_names(self) -> list[str]:
        return [str(item.get("fileName", "")) for item in self._items if item.get("fileName")]
