from __future__ import annotations

from bao.utils.attachments import (
    attachment_file_paths,
    normalize_attachment_records,
    persist_attachment_records,
)


def test_normalize_attachment_records_rehydrates_relative_record(tmp_path) -> None:
    attachment_dir = tmp_path / "artifacts"
    attachment_dir.mkdir()
    attachment_path = attachment_dir / "reply.png"
    attachment_path.write_bytes(b"png")

    records = [
        {
            "path": "artifacts/reply.png",
            "fileName": "friendly.png",
            "mimeType": "image/png",
            "size": 3,
            "isImage": True,
            "extensionLabel": "PNG",
        }
    ]

    normalized = normalize_attachment_records(records, workspace=tmp_path)

    assert normalized == [
        {
            "fileName": "friendly.png",
            "fileSizeLabel": "3 B",
            "filePath": str(attachment_path.resolve()),
            "previewUrl": attachment_path.resolve().as_uri(),
            "isImage": True,
            "extensionLabel": "PNG",
            "mimeType": "image/png",
            "sizeBytes": 3,
        }
    ]


def test_persist_attachment_records_and_file_paths_use_single_schema() -> None:
    records = [
        {
            "fileName": "friendly.png",
            "filePath": "/tmp/reply.png",
            "path": "artifacts/reply.png",
            "mimeType": "image/png",
            "sizeBytes": 12,
            "isImage": True,
            "extensionLabel": "PNG",
        }
    ]

    assert persist_attachment_records(records) == [
        {
            "fileName": "friendly.png",
            "path": "artifacts/reply.png",
            "mimeType": "image/png",
            "size": 12,
            "isImage": True,
            "extensionLabel": "PNG",
        }
    ]
    assert attachment_file_paths(records) == ["/tmp/reply.png"]
