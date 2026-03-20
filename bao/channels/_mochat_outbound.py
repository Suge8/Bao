"""Mochat outbound HTTP helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from loguru import logger

from bao.bus.events import OutboundMessage

from ._mochat_common import resolve_mochat_target


@dataclass(frozen=True)
class _MochatSendRequest:
    path: str
    id_key: str
    target_id: str
    content: str
    reply_to: str | None
    group_id: str | None = None


class _MochatOutboundMixin:
    async def send(self, msg: OutboundMessage) -> None:
        if not self.config.claw_token.get_secret_value():
            logger.warning("⚠️ Mochat 令牌缺失 / token missing: skip send")
            return

        parts = [msg.content.strip()] if msg.content and msg.content.strip() else []
        if msg.media:
            parts.extend(item for item in msg.media if isinstance(item, str) and item.strip())
        content = "\n".join(parts).strip()
        if not content:
            return

        target = resolve_mochat_target(msg.chat_id)
        if not target.id:
            logger.warning("⚠️ Mochat 发送目标为空 / target empty: outbound target is empty")
            return

        is_panel = (target.is_panel or target.id in self._panel_set) and not target.id.startswith(
            "session_"
        )
        try:
            if is_panel:
                await self._api_send(
                    _MochatSendRequest(
                        path="/api/claw/groups/panels/send",
                        id_key="panelId",
                        target_id=target.id,
                        content=content,
                        reply_to=msg.reply_to,
                        group_id=self._read_group_id(msg.metadata),
                    )
                )
            else:
                await self._api_send(
                    _MochatSendRequest(
                        path="/api/claw/sessions/send",
                        id_key="sessionId",
                        target_id=target.id,
                        content=content,
                        reply_to=msg.reply_to,
                    )
                )
        except Exception as exc:
            logger.error("❌ Mochat 消息发送失败 / send failed: {}", exc)

    async def _post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not self._http:
            raise RuntimeError("Mochat HTTP client not initialized")
        url = f"{self.config.base_url.strip().rstrip('/')}{path}"
        response = await self._http.post(
            url,
            headers={
                "Content-Type": "application/json",
                "X-Claw-Token": self.config.claw_token.get_secret_value(),
            },
            json=payload,
        )
        if not response.is_success:
            raise RuntimeError(f"Mochat HTTP {response.status_code}: {response.text[:200]}")
        try:
            parsed = response.json()
        except Exception:
            parsed = response.text
        if isinstance(parsed, dict) and isinstance(parsed.get("code"), int):
            if parsed["code"] != 200:
                message = str(parsed.get("message") or parsed.get("name") or "request failed")
                raise RuntimeError(f"Mochat API error: {message} (code={parsed['code']})")
            data = parsed.get("data")
            return data if isinstance(data, dict) else {}
        return parsed if isinstance(parsed, dict) else {}

    async def _api_send(self, request: _MochatSendRequest) -> dict[str, Any]:
        body: dict[str, Any] = {request.id_key: request.target_id, "content": request.content}
        if request.reply_to:
            body["replyTo"] = request.reply_to
        if request.group_id:
            body["groupId"] = request.group_id
        return await self._post_json(request.path, body)

    @staticmethod
    def _read_group_id(metadata: dict[str, Any]) -> str | None:
        if not isinstance(metadata, dict):
            return None
        value = metadata.get("group_id") or metadata.get("groupId")
        return value.strip() if isinstance(value, str) and value.strip() else None
