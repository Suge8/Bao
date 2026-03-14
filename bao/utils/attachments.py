from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Any


def format_attachment_size(size_bytes: int) -> str:
    size = float(max(0, int(size_bytes)))
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} TB"


def build_attachment_payload(path: str | Path) -> dict[str, Any] | None:
    raw_path = Path(path).expanduser()
    try:
        resolved = raw_path.resolve()
    except OSError:
        return None
    if not resolved.is_file():
        return None
    try:
        size_bytes = resolved.stat().st_size
    except OSError:
        return None
    mime_type, _ = mimetypes.guess_type(str(resolved))
    suffix = resolved.suffix.lower().lstrip(".")
    return {
        "fileName": resolved.name,
        "fileSizeLabel": format_attachment_size(size_bytes),
        "filePath": str(resolved),
        "previewUrl": resolved.as_uri(),
        "isImage": bool(mime_type and mime_type.startswith("image/")),
        "extensionLabel": (suffix[:4] or "FILE").upper(),
        "mimeType": mime_type or "",
        "sizeBytes": size_bytes,
    }


def build_attachment_payload_from_record(
    record: dict[str, Any],
    *,
    workspace: str | Path | None = None,
) -> dict[str, Any] | None:
    if not isinstance(record, dict):
        return None
    raw_path = record.get("filePath") or record.get("path")
    if not isinstance(raw_path, str) or not raw_path.strip():
        return None

    path = Path(raw_path).expanduser()
    if not path.is_absolute() and workspace is not None:
        path = Path(workspace).expanduser() / path

    payload = build_attachment_payload(path)
    if payload is None:
        size_bytes = record.get("sizeBytes", record.get("size"))
        safe_size = int(size_bytes) if isinstance(size_bytes, int) and size_bytes >= 0 else 0
        suffix = path.suffix.lower().lstrip(".")
        payload = {
            "fileName": path.name,
            "fileSizeLabel": format_attachment_size(safe_size),
            "filePath": str(path),
            "previewUrl": path.as_uri() if path.is_absolute() else "",
            "isImage": bool(record.get("isImage")),
            "extensionLabel": str(record.get("extensionLabel") or (suffix[:4] or "FILE")).upper(),
            "mimeType": str(record.get("mimeType") or ""),
            "sizeBytes": safe_size,
        }

    file_name = record.get("fileName") or record.get("name")
    if isinstance(file_name, str) and file_name.strip():
        payload["fileName"] = file_name.strip()
    if isinstance(record.get("mimeType"), str) and str(record["mimeType"]).strip():
        payload["mimeType"] = str(record["mimeType"]).strip()
    if isinstance(record.get("isImage"), bool):
        payload["isImage"] = bool(record["isImage"])
    if isinstance(record.get("extensionLabel"), str) and str(record["extensionLabel"]).strip():
        payload["extensionLabel"] = str(record["extensionLabel"]).strip().upper()
    size_bytes = record.get("sizeBytes", record.get("size"))
    if isinstance(size_bytes, int) and size_bytes >= 0:
        payload["sizeBytes"] = size_bytes
        payload["fileSizeLabel"] = format_attachment_size(size_bytes)
    return payload


def normalize_attachment_records(
    records: list[dict[str, Any]] | None,
    *,
    workspace: str | Path | None = None,
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for record in records or []:
        if not isinstance(record, dict):
            continue
        payload = build_attachment_payload_from_record(record, workspace=workspace)
        if isinstance(payload, dict):
            normalized.append(payload)
    return normalized


def persist_attachment_records(records: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    persisted: list[dict[str, Any]] = []
    for record in records or []:
        if not isinstance(record, dict):
            continue
        payload = {
            "fileName": record.get("fileName") or record.get("name"),
            "path": record.get("path") or record.get("filePath"),
            "mimeType": record.get("mimeType"),
            "size": record.get("size") or record.get("sizeBytes"),
            "isImage": record.get("isImage"),
            "extensionLabel": record.get("extensionLabel"),
        }
        persisted.append({key: value for key, value in payload.items() if value not in (None, "", [])})
    return persisted


def attachment_file_paths(records: list[dict[str, Any]] | None) -> list[str]:
    paths: list[str] = []
    for record in records or []:
        if not isinstance(record, dict):
            continue
        raw_path = record.get("filePath")
        if not isinstance(raw_path, str) or not raw_path.strip():
            continue
        paths.append(raw_path)
    return paths
