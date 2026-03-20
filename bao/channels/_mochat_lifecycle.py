"""Mochat lifecycle, subscription, and discovery helpers."""

from __future__ import annotations

import asyncio

import httpx
from loguru import logger

from ._mochat_common import _str_field


class _MochatLifecycleMixin:
    async def start(self) -> None:
        if not self.config.claw_token.get_secret_value():
            logger.error("❌ Mochat 配置缺失 / config missing: claw_token not configured")
            return

        self._start_lifecycle()
        self._http = httpx.AsyncClient(timeout=30.0)
        self._state_dir.mkdir(parents=True, exist_ok=True)
        await self._load_session_cursors()
        self._seed_targets_from_config()
        await self._refresh_targets()

        socket_started = await self._start_socket_client()
        await self._reconcile_transport_mode(
            "socket" if socket_started and self._ws_ready else "fallback"
        )

        self._refresh_task = asyncio.create_task(self._refresh_loop())
        await self._wait_until_stopped()

    async def stop(self) -> None:
        self._stop_lifecycle()
        if self._refresh_task:
            self._refresh_task.cancel()
            self._refresh_task = None

        await self._reconcile_transport_mode("stopped")
        await self._cancel_delay_timers()

        if self._socket:
            try:
                await self._socket.disconnect()
            except Exception:
                pass
            self._socket = None

        if self._cursor_save_task:
            self._cursor_save_task.cancel()
            self._cursor_save_task = None
        await self._save_session_cursors()

        if self._http:
            await self._http.aclose()
            self._http = None
        self._ws_connected = False
        self._ws_ready = False
        self._transport_mode = "stopped"
        self._reset_lifecycle()

    def _seed_targets_from_config(self) -> None:
        sessions, self._auto_discover_sessions = self._normalize_id_list(self.config.sessions)
        panels, self._auto_discover_panels = self._normalize_id_list(self.config.panels)
        self._session_set.update(sessions)
        self._panel_set.update(panels)
        for session_id in sessions:
            if session_id not in self._session_cursor:
                self._cold_sessions.add(session_id)

    @staticmethod
    def _normalize_id_list(values: list[str]) -> tuple[list[str], bool]:
        cleaned = [str(value).strip() for value in values if str(value).strip()]
        return sorted({value for value in cleaned if value != "*"}), "*" in cleaned

    async def _refresh_loop(self) -> None:
        interval_s = max(1.0, self.config.refresh_interval_ms / 1000.0)
        while self._running:
            if await self._wait_stop_or_timeout(interval_s):
                break
            try:
                await self._refresh_targets()
            except Exception as exc:
                logger.warning("⚠️ Mochat 刷新失败 / refresh failed: {}", exc)
            await self._reconcile_transport_mode(self._transport_mode)

    async def _refresh_targets(self) -> None:
        subscribe_new = self._transport_mode == "socket"
        if self._auto_discover_sessions:
            await self._refresh_sessions_directory(subscribe_new)
        if self._auto_discover_panels:
            await self._refresh_panels(subscribe_new)

    async def _refresh_sessions_directory(self, subscribe_new: bool) -> None:
        try:
            response = await self._post_json("/api/claw/sessions/list", {})
        except Exception as exc:
            logger.warning("⚠️ Mochat 会话拉取失败 / list failed: {}", exc)
            return

        sessions = response.get("sessions")
        if not isinstance(sessions, list):
            return

        new_ids: list[str] = []
        for item in sessions:
            if not isinstance(item, dict):
                continue
            session_id = _str_field(item, "sessionId")
            if not session_id:
                continue
            if session_id not in self._session_set:
                self._session_set.add(session_id)
                new_ids.append(session_id)
                if session_id not in self._session_cursor:
                    self._cold_sessions.add(session_id)
            converse_id = _str_field(item, "converseId")
            if converse_id:
                self._session_by_converse[converse_id] = session_id

        if new_ids and self._ws_ready and subscribe_new:
            await self._subscribe_sessions(new_ids)

    async def _refresh_panels(self, subscribe_new: bool) -> None:
        try:
            response = await self._post_json("/api/claw/groups/get", {})
        except Exception as exc:
            logger.warning("⚠️ Mochat 面板拉取失败 / panel fetch failed: {}", exc)
            return

        raw_panels = response.get("panels")
        if not isinstance(raw_panels, list):
            return

        new_ids: list[str] = []
        for item in raw_panels:
            if not isinstance(item, dict):
                continue
            panel_type = item.get("type")
            if isinstance(panel_type, int) and panel_type != 0:
                continue
            panel_id = _str_field(item, "id", "_id")
            if panel_id and panel_id not in self._panel_set:
                self._panel_set.add(panel_id)
                new_ids.append(panel_id)

        if new_ids and self._ws_ready and subscribe_new:
            await self._subscribe_panels(new_ids)

    async def _reconcile_transport_mode(self, mode: str) -> None:
        if mode not in {"socket", "fallback", "stopped"}:
            mode = "fallback"
        self._transport_mode = mode
        if mode == "fallback" and self._running:
            self._sync_fallback_workers()
            return
        await self._cancel_fallback_workers()

    def _sync_fallback_workers(self) -> None:
        desired_sessions = set(self._session_set)
        desired_panels = set(self._panel_set)

        for session_id, task in list(self._session_fallback_tasks.items()):
            if session_id in desired_sessions and not task.done():
                continue
            task.cancel()
            self._session_fallback_tasks.pop(session_id, None)
        for panel_id, task in list(self._panel_fallback_tasks.items()):
            if panel_id in desired_panels and not task.done():
                continue
            task.cancel()
            self._panel_fallback_tasks.pop(panel_id, None)

        for session_id in sorted(desired_sessions):
            if self._session_fallback_tasks.get(session_id) is None:
                self._session_fallback_tasks[session_id] = asyncio.create_task(
                    self._session_watch_worker(session_id)
                )
        for panel_id in sorted(desired_panels):
            if self._panel_fallback_tasks.get(panel_id) is None:
                self._panel_fallback_tasks[panel_id] = asyncio.create_task(
                    self._panel_poll_worker(panel_id)
                )

    async def _cancel_fallback_workers(self) -> None:
        tasks = [*self._session_fallback_tasks.values(), *self._panel_fallback_tasks.values()]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._session_fallback_tasks.clear()
        self._panel_fallback_tasks.clear()
