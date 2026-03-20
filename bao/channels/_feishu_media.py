"""Feishu media upload and download helpers."""

from __future__ import annotations

import asyncio
import os
from typing import Any

from loguru import logger


class _FeishuMediaMixin:
    _IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".ico", ".tiff", ".tif"}
    _AUDIO_EXTS = {".opus"}
    _VIDEO_EXTS = {".mp4", ".mov", ".avi"}
    _FILE_TYPE_MAP = {
        ".opus": "opus",
        ".mp4": "mp4",
        ".pdf": "pdf",
        ".doc": "doc",
        ".docx": "doc",
        ".xls": "xls",
        ".xlsx": "xls",
        ".ppt": "ppt",
        ".pptx": "ppt",
    }

    def _upload_image_sync(self, file_path: str) -> str | None:
        from . import feishu as feishu_module

        try:
            with open(file_path, "rb") as file_obj:
                request = (
                    feishu_module.CreateImageRequest.builder()
                    .request_body(
                        feishu_module.CreateImageRequestBody.builder()
                        .image_type("message")
                        .image(file_obj)
                        .build()
                    )
                    .build()
                )
                response = self._client.im.v1.image.create(request)
                if response.success():
                    image_key = response.data.image_key
                    logger.debug("Uploaded image {}: {}", os.path.basename(file_path), image_key)
                    return image_key
                logger.error(
                    "❌ 飞书图片上传失败 / upload failed: code={}, msg={}",
                    response.code,
                    response.msg,
                )
                return None
        except Exception as exc:
            logger.error("❌ 飞书图片上传异常 / upload error: {}: {}", file_path, exc)
            return None

    def _upload_file_sync(self, file_path: str) -> str | None:
        from . import feishu as feishu_module

        ext = os.path.splitext(file_path)[1].lower()
        file_type = self._FILE_TYPE_MAP.get(ext, "stream")
        file_name = os.path.basename(file_path)
        try:
            with open(file_path, "rb") as file_obj:
                request = (
                    feishu_module.CreateFileRequest.builder()
                    .request_body(
                        feishu_module.CreateFileRequestBody.builder()
                        .file_type(file_type)
                        .file_name(file_name)
                        .file(file_obj)
                        .build()
                    )
                    .build()
                )
                response = self._client.im.v1.file.create(request)
                if response.success():
                    file_key = response.data.file_key
                    logger.debug("Uploaded file {}: {}", file_name, file_key)
                    return file_key
                logger.error(
                    "❌ 飞书文件上传失败 / upload failed: code={}, msg={}",
                    response.code,
                    response.msg,
                )
                return None
        except Exception as exc:
            logger.error("❌ 飞书文件上传异常 / upload error: {}: {}", file_path, exc)
            return None

    def _download_image_sync(
        self,
        message_id: str,
        image_key: str,
    ) -> tuple[bytes | None, str | None]:
        from . import feishu as feishu_module

        try:
            request = (
                feishu_module.GetMessageResourceRequest.builder()
                .message_id(message_id)
                .file_key(image_key)
                .type("image")
                .build()
            )
            response = self._client.im.v1.message_resource.get(request)
            if response.success():
                file_data = response.file
                if hasattr(file_data, "read"):
                    file_data = file_data.read()
                return file_data, response.file_name
            logger.error(
                "❌ 飞书图片下载失败 / download failed: code={}, msg={}",
                response.code,
                response.msg,
            )
            return None, None
        except Exception as exc:
            logger.error("❌ 飞书图片下载异常 / download error: {}: {}", image_key, exc)
            return None, None

    def _download_file_sync(self, file_key: str) -> tuple[bytes | None, str | None]:
        from . import feishu as feishu_module

        try:
            request = feishu_module.GetFileRequest.builder().file_key(file_key).build()
            response = self._client.im.v1.file.get(request)
            if response.success():
                return response.file, response.file_name
            logger.error(
                "❌ 飞书文件下载失败 / download failed: code={}, msg={}",
                response.code,
                response.msg,
            )
            return None, None
        except Exception as exc:
            logger.error("❌ 飞书文件下载异常 / download error: {}: {}", file_key, exc)
            return None, None

    async def _download_and_save_media(
        self,
        msg_type: str,
        content_json: dict[str, Any],
        message_id: str | None = None,
    ) -> tuple[str | None, str]:
        from . import feishu as feishu_module

        loop = asyncio.get_running_loop()
        media_dir = feishu_module.get_media_dir("feishu")
        data, filename = None, None

        if msg_type == "image":
            image_key = content_json.get("image_key")
            if image_key and message_id:
                data, filename = await loop.run_in_executor(
                    None,
                    self._download_image_sync,
                    message_id,
                    image_key,
                )
                if not filename:
                    filename = f"{image_key[:16]}.jpg"
        elif msg_type in ("audio", "file", "media"):
            file_key = content_json.get("file_key")
            if file_key:
                data, filename = await loop.run_in_executor(None, self._download_file_sync, file_key)
                if not filename:
                    ext = {"audio": ".opus", "media": ".mp4"}.get(msg_type, "")
                    filename = f"{file_key[:16]}{ext}"
                if msg_type == "audio" and not filename.endswith(".opus"):
                    filename = f"{filename}.opus"

        if data and filename:
            file_path = media_dir / filename
            file_path.write_bytes(data)
            logger.debug("Downloaded {} to {}", msg_type, file_path)
            return str(file_path), f"[{msg_type}: {filename}]"

        return None, f"[{msg_type}: download failed]"
