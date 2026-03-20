"""Mochat socket subscription helpers."""

from __future__ import annotations

import math
from typing import Any

from loguru import logger

from ._mochat_common import MSGPACK_AVAILABLE, SOCKETIO_AVAILABLE, socketio


class _MochatSocketMixin:
    async def _start_socket_client(self) -> bool:
        if not SOCKETIO_AVAILABLE:
            logger.warning("⚠️ Mochat SocketIO 未安装 / socketio missing: using polling fallback")
            return False
        assert socketio is not None

        client = self._build_socket_client(self._resolve_socket_serializer())
        self._register_socket_handlers(client)

        try:
            self._socket = client
            await client.connect(**self._socket_connect_kwargs())
            return True
        except Exception as exc:
            logger.error("❌ Mochat 连接异常 / ws connect failed: {}", exc)
            try:
                await client.disconnect()
            except Exception:
                pass
            self._socket = None
            return False

    def _resolve_socket_serializer(self) -> str:
        if self.config.socket_disable_msgpack:
            return "default"
        if MSGPACK_AVAILABLE:
            return "msgpack"
        logger.warning(
            "⚠️ Mochat Msgpack 未安装 / msgpack missing: socket_disable_msgpack=false, using JSON"
        )
        return "default"

    def _build_socket_client(self, serializer: str):
        assert socketio is not None
        return socketio.AsyncClient(
            reconnection=True,
            reconnection_attempts=max(0, self.config.max_retry_attempts),
            reconnection_delay=max(1, math.ceil(self.config.socket_reconnect_delay_ms / 1000.0)),
            reconnection_delay_max=max(
                1,
                math.ceil(self.config.socket_max_reconnect_delay_ms / 1000.0),
            ),
            logger=False,
            engineio_logger=False,
            serializer=serializer,
        )

    def _register_socket_handlers(self, client) -> None:
        @client.event
        async def connect() -> None:
            await self._on_socket_connect()

        @client.event
        async def disconnect() -> None:
            await self._on_socket_disconnect()

        @client.event
        async def connect_error(data: Any) -> None:
            logger.error("❌ Mochat 连接失败 / ws connect error: {}", data)

        client.on("claw.session.events", handler=self._handle_session_events)
        client.on("claw.panel.events", handler=self._handle_panel_events)
        for event_name in self._notify_event_names():
            client.on(event_name, self._build_notify_handler(event_name))

    async def _on_socket_connect(self) -> None:
        self._ws_connected = True
        self._ws_ready = False
        logger.info("✅ Mochat 已连接 / ws connected: websocket connected")
        subscribed = await self._subscribe_all()
        self._ws_ready = subscribed
        await self._reconcile_transport_mode("socket" if subscribed else "fallback")

    async def _on_socket_disconnect(self) -> None:
        if not self._running:
            return
        self._ws_connected = False
        self._ws_ready = False
        logger.info("ℹ️ Mochat 已断开 / ws disconnected: websocket disconnected")
        await self._reconcile_transport_mode("fallback")

    async def _handle_session_events(self, payload: dict[str, Any]) -> None:
        await self._handle_watch_payload(payload, "session")

    async def _handle_panel_events(self, payload: dict[str, Any]) -> None:
        await self._handle_watch_payload(payload, "panel")

    @staticmethod
    def _notify_event_names() -> tuple[str, ...]:
        return (
            "notify:chat.inbox.append",
            "notify:chat.message.add",
            "notify:chat.message.update",
            "notify:chat.message.recall",
            "notify:chat.message.delete",
        )

    def _socket_connect_kwargs(self) -> dict[str, Any]:
        socket_url = (self.config.socket_url or self.config.base_url).strip().rstrip("/")
        socket_path = (self.config.socket_path or "/socket.io").strip().lstrip("/")
        return {
            "url": socket_url,
            "transports": ["websocket"],
            "socketio_path": socket_path,
            "auth": {"token": self.config.claw_token.get_secret_value()},
            "wait_timeout": max(1, math.ceil(self.config.socket_connect_timeout_ms / 1000.0)),
        }

    def _build_notify_handler(self, event_name: str):
        async def handler(payload: Any) -> None:
            if event_name == "notify:chat.inbox.append":
                await self._handle_notify_inbox_append(payload)
            elif event_name.startswith("notify:chat.message."):
                await self._handle_notify_chat_message(payload)

        return handler

    async def _subscribe_all(self) -> bool:
        ok = await self._subscribe_sessions(sorted(self._session_set))
        ok = await self._subscribe_panels(sorted(self._panel_set)) and ok
        if self._auto_discover_sessions or self._auto_discover_panels:
            await self._refresh_targets()
        return ok

    async def _subscribe_sessions(self, session_ids: list[str]) -> bool:
        if not session_ids:
            return True
        for session_id in session_ids:
            if session_id not in self._session_cursor:
                self._cold_sessions.add(session_id)

        ack = await self._socket_call(
            "com.claw.im.subscribeSessions",
            {
                "sessionIds": session_ids,
                "cursors": self._session_cursor,
                "limit": self.config.watch_limit,
            },
        )
        if not ack.get("result"):
            logger.error(
                "❌ Mochat 订阅会话失败 / subscribe failed: {}",
                ack.get("message", "unknown error"),
            )
            return False

        data = ack.get("data")
        items: list[dict[str, Any]] = []
        if isinstance(data, list):
            items = [item for item in data if isinstance(item, dict)]
        elif isinstance(data, dict):
            sessions = data.get("sessions")
            if isinstance(sessions, list):
                items = [item for item in sessions if isinstance(item, dict)]
            elif "sessionId" in data:
                items = [data]
        for payload in items:
            await self._handle_watch_payload(payload, "session")
        return True

    async def _subscribe_panels(self, panel_ids: list[str]) -> bool:
        if not self._auto_discover_panels and not panel_ids:
            return True
        ack = await self._socket_call("com.claw.im.subscribePanels", {"panelIds": panel_ids})
        if not ack.get("result"):
            logger.error(
                "❌ Mochat 订阅面板失败 / subscribe failed: {}",
                ack.get("message", "unknown error"),
            )
            return False
        return True

    async def _socket_call(self, event_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not self._socket:
            return {"result": False, "message": "socket not connected"}
        try:
            raw = await self._socket.call(event_name, payload, timeout=10)
        except Exception as exc:
            return {"result": False, "message": str(exc)}
        return raw if isinstance(raw, dict) else {"result": True, "data": raw}
