"""Slack outbound helpers."""

from __future__ import annotations

from loguru import logger

from bao.bus.events import OutboundMessage


class _SlackOutboundMixin:
    def _resolve_thread_ts(self, msg: OutboundMessage) -> str | None:
        slack_meta = msg.metadata.get("slack", {}) if msg.metadata else {}
        thread_ts = slack_meta.get("thread_ts")
        channel_type = slack_meta.get("channel_type")
        return thread_ts if thread_ts and channel_type != "im" else None

    async def send(self, msg: OutboundMessage) -> None:
        if not self._web_client:
            logger.warning("⚠️ 未运行 / client not running: Slack client")
            return
        try:
            thread_ts_param = self._resolve_thread_ts(msg)
            self._progress_threads[msg.chat_id] = thread_ts_param

            await self._dispatch_progress_text(msg, flush_progress=True)

            for media_path in msg.media or []:
                try:
                    await self._web_client.files_upload_v2(
                        channel=msg.chat_id,
                        file=media_path,
                        thread_ts=thread_ts_param,
                    )
                except Exception as exc:
                    logger.error("❌ 上传失败 / upload failed: {}: {}", media_path, exc)
            meta = msg.metadata or {}
            if bool(meta.get("_progress_clear")) or not bool(meta.get("_progress")):
                self._progress_threads.pop(msg.chat_id, None)
        except Exception as exc:
            logger.error("❌ 发送失败 / send failed: {}", exc)

    async def _send_text(self, chat_id: str, text: str) -> None:
        if not self._web_client or not text:
            return
        await self._web_client.chat_postMessage(
            channel=chat_id,
            text=self._to_mrkdwn(text),
            thread_ts=self._progress_threads.get(chat_id),
        )

    async def _create_progress_text(self, chat_id: str, text: str) -> str | None:
        if not self._web_client or not text:
            return None
        response = await self._web_client.chat_postMessage(
            channel=chat_id,
            text=self._to_mrkdwn(text),
            thread_ts=self._progress_threads.get(chat_id),
        )
        return response.get("ts") if isinstance(response, dict) else None

    async def _update_progress_text(
        self,
        chat_id: str,
        handle: str | None,
        text: str,
    ) -> str | None:
        if not self._web_client or not handle or not text:
            return handle
        await self._web_client.chat_update(
            channel=chat_id,
            ts=handle,
            text=self._to_mrkdwn(text),
        )
        return handle
