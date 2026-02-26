"""Image generation tool using Gemini-compatible API."""

import base64
import tempfile
from typing import Any

import httpx
from loguru import logger

from bao.agent.tools.base import Tool

_DEFAULT_MODEL = "gemini-2.0-flash-exp-image-generation"
_DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
_TIMEOUT = 60


class ImageGenTool(Tool):
    """Generate images from text prompts via Gemini API."""

    def __init__(self, api_key: str, model: str = "", base_url: str = ""):
        self._api_key = api_key
        self._model = model or _DEFAULT_MODEL
        self._base_url = (base_url or _DEFAULT_BASE_URL).rstrip("/")

    @property
    def name(self) -> str:
        return "generate_image"

    @property
    def description(self) -> str:
        return (
            "Generate an image from a text prompt. "
            "Returns a local file path. Send it via message(media=[path])."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Text description of the image to generate",
                },
                "aspect_ratio": {
                    "type": "string",
                    "description": "Aspect ratio, e.g. 1:1, 16:9, 9:16",
                },
            },
            "required": ["prompt"],
        }

    async def execute(self, prompt: str, aspect_ratio: str = "", **kwargs: Any) -> str:
        url = f"{self._base_url}/models/{self._model}:generateContent?key={self._api_key}"
        payload: dict[str, Any] = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseModalities": ["IMAGE", "TEXT"]},
        }
        if aspect_ratio:
            payload["generationConfig"]["aspectRatio"] = aspect_ratio

        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.post(url, json=payload)
        except Exception as e:
            return f"Error: image generation failed: {e}"

        if resp.status_code != 200:
            body = resp.text[:300]
            logger.warning("generate_image API error {}: {}", resp.status_code, body)
            return f"Error: API returned {resp.status_code}. {body}"

        return self._parse_response(resp.json())

    def _parse_response(self, data: dict[str, Any]) -> str:
        """Extract image from API response, save to temp file, return path."""
        for candidate in data.get("candidates", []):
            for part in candidate.get("content", {}).get("parts", []):
                inline = part.get("inlineData")
                if inline and inline.get("data"):
                    mime = inline.get("mimeType", "image/png")
                    suffix = ".webp" if "webp" in mime else (".png" if "png" in mime else ".jpg")
                    try:
                        img_bytes = base64.b64decode(inline["data"])
                    except Exception:
                        return "Error: failed to decode image data."
                    with tempfile.NamedTemporaryFile(
                        delete=False, suffix=suffix, prefix="bao_img_"
                    ) as f:
                        f.write(img_bytes)
                        path = f.name
                    logger.info("generate_image: saved {} ({} bytes)", path, len(img_bytes))
                    return f"Image saved: {path}\nSend via message(media=['{path}'])"

        # No image — check for text fallback
        for candidate in data.get("candidates", []):
            for part in candidate.get("content", {}).get("parts", []):
                if part.get("text"):
                    return f"No image generated. Model said: {part['text'][:300]}"

        return "Error: no image data in API response."
