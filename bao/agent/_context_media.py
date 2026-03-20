from __future__ import annotations

import base64
import importlib
import logging
import mimetypes
from pathlib import Path
from typing import Any


class ContextMediaMixin:
    _SUPPORTED_IMAGE_MIMES = frozenset({"image/jpeg", "image/png", "image/gif", "image/webp"})
    _MAX_IMAGE_LONG_EDGE = 1568
    _MAX_IMAGE_BYTES = 1_000_000

    @staticmethod
    def _compress_image(p: Path, mime: str) -> tuple[str, str]:
        from io import BytesIO

        from PIL import Image, ImageOps

        try:
            pillow_heif = importlib.import_module("pillow_heif")
            register_heif_opener = getattr(pillow_heif, "register_heif_opener", None)
            if callable(register_heif_opener):
                register_heif_opener()
        except Exception:
            pass

        with Image.open(p) as img:
            img = ImageOps.exif_transpose(img)
            if max(img.size) > ContextMediaMixin._MAX_IMAGE_LONG_EDGE:
                img.thumbnail((ContextMediaMixin._MAX_IMAGE_LONG_EDGE, ContextMediaMixin._MAX_IMAGE_LONG_EDGE))
            if img.mode in ("RGBA", "LA", "PA"):
                background = Image.new("RGB", img.size, (255, 255, 255))
                background.paste(img, mask=img.split()[-1])
                img = background
            elif img.mode not in ("RGB", "L"):
                img = img.convert("RGB")
            buf = BytesIO()
            img.save(buf, format="JPEG", quality=85)
            return base64.b64encode(buf.getvalue()).decode(), "image/jpeg"

    def _build_user_content(self, text: str, media: list[str] | None) -> str | list[dict[str, Any]]:
        if not media:
            return text
        images = []
        for path in media:
            image = self._media_image_part(path)
            if image is not None:
                images.append(image)
        if not images:
            return text
        return images + [{"type": "text", "text": text}]

    def _media_image_part(self, path: str) -> dict[str, Any] | None:
        file_path = Path(path)
        mime, _ = mimetypes.guess_type(path)
        if not file_path.is_file() or not mime or not mime.startswith("image/"):
            return None
        encoded = self._encoded_media_bytes(file_path, mime)
        if encoded is None:
            return None
        image_b64, encoded_mime = encoded
        return {"type": "image_url", "image_url": {"url": f"data:{encoded_mime};base64,{image_b64}"}}

    def _encoded_media_bytes(self, file_path: Path, mime: str) -> tuple[str, str] | None:
        needs_transcode = mime not in self._SUPPORTED_IMAGE_MIMES
        try:
            needs_compress = file_path.stat().st_size > self._MAX_IMAGE_BYTES
        except OSError:
            return None
        if needs_transcode or needs_compress:
            try:
                return self._compress_image(file_path, mime)
            except ImportError:
                logging.warning("Pillow is not installed; skipping image %s", file_path)
                return None
            except Exception:
                logging.warning("Failed to process image %s", file_path, exc_info=True)
                return None
        try:
            return base64.b64encode(file_path.read_bytes()).decode(), mime
        except OSError:
            return None
