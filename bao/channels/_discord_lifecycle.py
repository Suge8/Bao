"""Discord lifecycle and gateway helpers."""

from __future__ import annotations

import asyncio

import httpx
from loguru import logger

from ._discord_common import _json


class _DiscordLifecycleMixin:
    async def start(self) -> None:
        if not self.config.token.get_secret_value():
            logger.error("❌ 未配置 / not configured: Discord token")
            return

        self._start_lifecycle()
        self._http = httpx.AsyncClient(timeout=30.0)

        async def run_once() -> None:
            from . import discord as discord_module

            url = self._resume_gateway_url or self.config.gateway_url
            logger.info("📡 连接网关 / connecting: Discord gateway")
            async with discord_module.websockets.connect(url) as ws:
                self._ws = ws
                try:
                    await self._gateway_loop()
                finally:
                    self._ws = None

        await self._run_reconnect_loop(run_once, label="Discord 网关")

    async def stop(self) -> None:
        self._clear_progress()
        self._progress_reply_to.clear()
        self._stop_lifecycle()
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            self._heartbeat_task = None
        for task in self._typing_tasks.values():
            task.cancel()
        self._typing_tasks.clear()
        if self._ws:
            await self._ws.close()
            self._ws = None
        if self._http:
            await self._http.aclose()
            self._http = None
        self._reset_lifecycle()

    async def _gateway_loop(self) -> None:
        if not self._ws:
            return

        async for raw in self._ws:
            data = self._parse_gateway_payload(raw)
            if data is None:
                continue
            should_break = await self._handle_gateway_payload(data)
            if should_break:
                break

    @staticmethod
    def _parse_gateway_payload(raw: str) -> dict[str, object] | None:
        import json

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            logger.debug("Invalid JSON from Discord gateway: {}", raw[:100])
            return None
        return parsed if isinstance(parsed, dict) else None

    async def _handle_gateway_payload(self, data: dict[str, object]) -> bool:
        op = data.get("op")
        event_type = data.get("t")
        seq = data.get("s")
        payload = data.get("d")

        if isinstance(seq, int):
            self._seq = seq

        if op == 10 and isinstance(payload, dict):
            interval_ms = payload.get("heartbeat_interval", 45000)
            await self._start_heartbeat(float(interval_ms) / 1000)
            if self._should_resume and self._session_id:
                await self._resume()
            else:
                await self._identify()
            return False
        if op == 11:
            self._heartbeat_acked = True
            return False
        if op == 0 and event_type == "READY" and isinstance(payload, dict):
            self._session_id = payload.get("session_id")
            self._resume_gateway_url = payload.get("resume_gateway_url")
            user = payload.get("user") or {}
            self._bot_user_id = str(user.get("id")) if isinstance(user, dict) and user.get("id") else None
            self._should_resume = True
            logger.debug("Discord gateway READY (session={})", self._session_id)
            return False
        if op == 0 and event_type == "RESUMED":
            logger.debug("Discord gateway RESUMED successfully")
            return False
        if op == 0 and event_type == "MESSAGE_CREATE" and isinstance(payload, dict):
            await self._handle_message_create(payload)
            return False
        if op == 7:
            logger.info("🔄 收到重连 / reconnect requested: Discord gateway")
            self._should_resume = True
            return True
        if op == 9:
            resumable = payload is True
            logger.warning("⚠️ 会话失效 / invalid session: resumable={}", resumable)
            self._should_resume = resumable
            if not resumable:
                self._session_id = None
                self._resume_gateway_url = None
            await asyncio.sleep(1 + 4 * (not resumable))
            return True
        return False

    async def _identify(self) -> None:
        if not self._ws:
            return
        identify = {
            "op": 2,
            "d": {
                "token": self.config.token.get_secret_value(),
                "intents": self.config.intents,
                "properties": {"os": "Bao", "browser": "Bao", "device": "Bao"},
            },
        }
        await self._ws.send(_json(identify))

    async def _resume(self) -> None:
        if not self._ws:
            return
        resume = {
            "op": 6,
            "d": {
                "token": self.config.token.get_secret_value(),
                "session_id": self._session_id,
                "seq": self._seq,
            },
        }
        logger.debug("Discord sending RESUME (seq={})", self._seq)
        await self._ws.send(_json(resume))

    async def _start_heartbeat(self, interval_s: float) -> None:
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
        self._heartbeat_acked = True

        async def heartbeat_loop() -> None:
            while self._running and self._ws:
                if not self._heartbeat_acked:
                    logger.debug("Discord heartbeat ACK not received — zombie connection, reconnecting")
                    await self._ws.close()
                    break
                self._heartbeat_acked = False
                try:
                    await self._ws.send(_json({"op": 1, "d": self._seq}))
                except Exception as exc:
                    logger.debug("Discord heartbeat failed: {}", exc)
                    break
                await asyncio.sleep(interval_s)

        self._heartbeat_task = asyncio.create_task(heartbeat_loop())
