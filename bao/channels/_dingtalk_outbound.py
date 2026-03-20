"""DingTalk outbound helpers."""

from __future__ import annotations

import asyncio
import mimetypes
import time
from pathlib import Path
from typing import Any

from loguru import logger

from bao.bus.events import OutboundMessage

from ._dingtalk_types import DingTalkSendRequest, DingTalkUploadRequest


class _DingTalkOutboundMixin:
    async def _get_access_token(self) -> str | None:
        if self._access_token and time.time() < self._token_expiry:
            return self._access_token

        url = "https://api.dingtalk.com/v1.0/oauth2/accessToken"
        data = {
            "appKey": self.config.client_id,
            "appSecret": self.config.client_secret.get_secret_value(),
        }
        if not self._http:
            logger.warning("⚠️ 钉钉客户端未就绪 / client not ready: cannot refresh token")
            return None

        try:
            response = await self._http.post(url, json=data)
            response.raise_for_status()
            res_data = response.json()
            self._access_token = res_data.get("accessToken")
            self._token_expiry = time.time() + int(res_data.get("expireIn", 7200)) - 60
            return self._access_token
        except Exception as exc:
            logger.error("❌ 钉钉令牌获取失败 / token failed: {}", exc)
            return None

    async def _read_media_bytes(
        self,
        media_ref: str,
    ) -> tuple[bytes | None, str | None, str | None]:
        if not media_ref:
            return None, None, None

        if self._is_http_url(media_ref):
            return await self._read_remote_media(media_ref)
        return await self._read_local_media(media_ref)

    async def _read_remote_media(
        self,
        media_ref: str,
    ) -> tuple[bytes | None, str | None, str | None]:
        if not self._http:
            return None, None, None
        try:
            response = await self._http.get(media_ref, follow_redirects=True)
            if response.status_code >= 400:
                logger.warning(
                    "DingTalk media download failed status={} ref={}",
                    response.status_code,
                    media_ref,
                )
                return None, None, None
            content_type = (response.headers.get("content-type") or "").split(";")[0].strip()
            filename = self._guess_filename(media_ref, self._guess_upload_type(media_ref))
            return response.content, filename, content_type or None
        except Exception as exc:
            logger.error("DingTalk media download error ref={} err={}", media_ref, exc)
            return None, None, None

    async def _read_local_media(
        self,
        media_ref: str,
    ) -> tuple[bytes | None, str | None, str | None]:
        try:
            local_path = self._resolve_local_media_path(media_ref)
            if not local_path.is_file():
                logger.warning("DingTalk media file not found: {}", local_path)
                return None, None, None
            data = await asyncio.to_thread(local_path.read_bytes)
            content_type = mimetypes.guess_type(local_path.name)[0]
            return data, local_path.name, content_type
        except Exception as exc:
            logger.error("DingTalk media read error ref={} err={}", media_ref, exc)
            return None, None, None

    async def _upload_media(self, request: DingTalkUploadRequest) -> str | None:
        if not self._http:
            return None
        url = (
            "https://oapi.dingtalk.com/media/upload"
            f"?access_token={request.token}&type={request.media_type}"
        )
        mime = (
            request.content_type
            or mimetypes.guess_type(request.filename)[0]
            or "application/octet-stream"
        )
        files = {"media": (request.filename, request.data, mime)}

        try:
            response = await self._http.post(url, files=files)
            text = response.text
            result = (
                response.json()
                if response.headers.get("content-type", "").startswith("application/json")
                else {}
            )
            if response.status_code >= 400:
                logger.error(
                    "DingTalk media upload failed status={} type={} body={}",
                    response.status_code,
                    request.media_type,
                    text[:500],
                )
                return None
            errcode = result.get("errcode", 0)
            if errcode != 0:
                logger.error(
                    "DingTalk media upload api error type={} errcode={} body={}",
                    request.media_type,
                    errcode,
                    text[:500],
                )
                return None
            sub = result.get("result") or {}
            media_id = (
                result.get("media_id")
                or result.get("mediaId")
                or sub.get("media_id")
                or sub.get("mediaId")
            )
            if not media_id:
                logger.error("DingTalk media upload missing media_id body={}", text[:500])
                return None
            return str(media_id)
        except Exception as exc:
            logger.error("DingTalk media upload error type={} err={}", request.media_type, exc)
            return None

    async def _send_batch_message(self, request: DingTalkSendRequest) -> bool:
        if not self._http:
            logger.warning("DingTalk HTTP client not initialized, cannot send")
            return False

        headers = {"x-acs-dingtalk-access-token": request.token}
        if request.chat_id.startswith("group:"):
            url = "https://api.dingtalk.com/v1.0/robot/groupMessages/send"
            payload = {
                "robotCode": self.config.client_id,
                "openConversationId": request.chat_id[6:],
                "msgKey": request.msg_key,
                "msgParam": self._encode_message_payload(request.msg_param),
            }
        else:
            url = "https://api.dingtalk.com/v1.0/robot/oToMessages/batchSend"
            payload = {
                "robotCode": self.config.client_id,
                "userIds": [request.chat_id],
                "msgKey": request.msg_key,
                "msgParam": self._encode_message_payload(request.msg_param),
            }

        try:
            response = await self._http.post(url, json=payload, headers=headers)
            body = response.text
            if response.status_code != 200:
                logger.error(
                    "DingTalk send failed msgKey={} status={} body={}",
                    request.msg_key,
                    response.status_code,
                    body[:500],
                )
                return False
            try:
                result = response.json()
            except Exception:
                result = {}
            errcode = result.get("errcode")
            if errcode not in (None, 0):
                logger.error(
                    "DingTalk send api error msgKey={} errcode={} body={}",
                    request.msg_key,
                    errcode,
                    body[:500],
                )
                return False
            logger.debug("DingTalk message sent to {} with msgKey={}", request.chat_id, request.msg_key)
            return True
        except Exception as exc:
            logger.error("Error sending DingTalk message msgKey={} err={}", request.msg_key, exc)
            return False

    @staticmethod
    def _encode_message_payload(msg_param: dict[str, Any]) -> str:
        import json

        return json.dumps(msg_param, ensure_ascii=False)

    async def _send_markdown_text(self, token: str, chat_id: str, content: str) -> bool:
        return await self._send_batch_message(
            DingTalkSendRequest(
                token=token,
                chat_id=chat_id,
                msg_key="sampleMarkdown",
                msg_param={"text": content, "title": "Bao Reply"},
            )
        )

    async def _send_media_ref(self, token: str, chat_id: str, media_ref: str) -> bool:
        media_ref = (media_ref or "").strip()
        if not media_ref:
            return True

        upload_type = self._guess_upload_type(media_ref)
        if upload_type == "image" and self._is_http_url(media_ref):
            if await self._send_batch_message(
                DingTalkSendRequest(
                    token=token,
                    chat_id=chat_id,
                    msg_key="sampleImageMsg",
                    msg_param={"photoURL": media_ref},
                )
            ):
                return True
            logger.warning("DingTalk image url send failed, trying upload fallback: {}", media_ref)

        data, filename, content_type = await self._read_media_bytes(media_ref)
        if not data:
            logger.error("DingTalk media read failed: {}", media_ref)
            return False

        filename = filename or self._guess_filename(media_ref, upload_type)
        file_type = self._resolve_file_type(filename, content_type)
        media_id = await self._upload_media(
            DingTalkUploadRequest(
                token=token,
                data=data,
                media_type=upload_type,
                filename=filename,
                content_type=content_type,
            )
        )
        if not media_id:
            return False

        return await self._send_batch_message(
            DingTalkSendRequest(
                token=token,
                chat_id=chat_id,
                msg_key="sampleFile",
                msg_param={"mediaId": media_id, "fileName": filename, "fileType": file_type},
            )
        )

    @staticmethod
    def _resolve_file_type(filename: str, content_type: str | None) -> str:
        file_type = Path(filename).suffix.lower().lstrip(".")
        if not file_type:
            guessed = mimetypes.guess_extension(content_type or "")
            file_type = (guessed or ".bin").lstrip(".")
        return "jpg" if file_type == "jpeg" else file_type

    async def send(self, msg: OutboundMessage) -> None:
        token = await self._get_access_token()
        if not token:
            return

        self._progress_token = token
        await self._dispatch_progress_text(msg, flush_progress=False)

        for media_ref in msg.media or []:
            if await self._send_media_ref(token, msg.chat_id, media_ref):
                continue
            logger.error("DingTalk media send failed for {}", media_ref)
            filename = self._guess_filename(media_ref, self._guess_upload_type(media_ref))
            await self._send_markdown_text(
                token,
                msg.chat_id,
                f"[Attachment send failed: {filename}]",
            )

    async def _send_text(self, chat_id: str, text: str) -> None:
        token = getattr(self, "_progress_token", None)
        if not token or not text.strip():
            return
        await self._send_markdown_text(token, chat_id, text.strip())
