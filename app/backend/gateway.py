"""ChatService — embedded Bao gateway lifecycle + serial message queue.

State machine: idle -> starting -> running -> stopped / error

Full gateway: AgentLoop + ChannelManager + CronService + HeartbeatService,
functionally equivalent to the CLI ``bao`` command.
All Bao core calls happen on the asyncio thread via AsyncioRunner.
Internal signals marshal results back to the Qt main thread.
"""

from __future__ import annotations

import asyncio
import copy
import os
import queue
import threading
from collections import OrderedDict
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger
from PySide6.QtCore import Property, QObject, QTimer, Signal, Slot

from app.backend.asyncio_runner import AsyncioRunner
from app.backend.chat import ChatMessageModel
from bao.gateway.builder import DesktopStartupMessage
from bao.session.manager import SessionChangeEvent

_DEBUG_SWITCH = os.getenv("BAO_DESKTOP_DEBUG_SWITCH") == "1"
_PROFILE = os.getenv("BAO_DESKTOP_PROFILE") == "1"

_HISTORY_FULL_LIMIT = 200
_HISTORY_CACHE_LIMIT = 16
_GATEWAY_CHANNEL_ORDER = (
    "telegram",
    "discord",
    "whatsapp",
    "feishu",
    "slack",
    "email",
    "qq",
    "dingtalk",
    "imessage",
)
_CHANNEL_ERROR_LABELS = {
    "unavailable": ("通道不可用", "Channel unavailable"),
    "start_failed": ("通道启动失败", "Channel start failed"),
    "send_failed": ("通道发送失败", "Channel send failed"),
    "stop_failed": ("通道停止失败", "Channel stop failed"),
}


def _normalize_gateway_channels(channels: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for name in _GATEWAY_CHANNEL_ORDER:
        if name in channels and name not in seen:
            ordered.append(name)
            seen.add(name)
    for name in channels:
        if name not in seen:
            ordered.append(name)
            seen.add(name)
    return ordered


@dataclass(frozen=True)
class _QueuedUiMessage:
    role: str
    content: str
    session_key: str = ""
    status: str = "done"
    entrance_style: str = "none"

    @classmethod
    def from_startup(
        cls, message: DesktopStartupMessage, session_key: str = ""
    ) -> _QueuedUiMessage:
        return cls(
            role=message.role,
            content=message.content,
            session_key=session_key,
            entrance_style=message.entrance_style,
        )

    def with_session_key(self, session_key: str) -> _QueuedUiMessage:
        return replace(self, session_key=session_key)


@dataclass(frozen=True)
class _HistorySnapshot:
    fingerprint: tuple[int, str]
    prepared_messages: list[dict[str, Any]]
    has_messages: bool


class ChatService(QObject):
    stateChanged = Signal(str)
    errorChanged = Signal(str)
    gatewayDetailChanged = Signal(str)
    gatewayChannelsChanged = Signal()
    messageAppended = Signal(int)
    contentUpdated = Signal(int, str)
    statusUpdated = Signal(int, str)
    gatewayReady = Signal(object, list)  # session_manager, enabled_channels
    historyLoadingChanged = Signal(bool)
    activeSessionStateChanged = Signal()
    sessionViewApplied = Signal(str)

    # Internal signals: asyncio thread → Qt main thread marshaling
    _initResult = Signal(int, bool, str, object, list)
    _sendResult = Signal(int, bool, str)  # row, ok, content_or_error
    _historyResult = Signal(bool, str, object)  # ok, error, messages_list
    _progressUpdate = Signal(int, str)  # row, accumulated_content (asyncio → Qt)
    _toolHintUpdate = Signal(str)
    _systemResponse = Signal(str, str)
    _startupMessage = Signal(object)
    _controlPlaneError = Signal(str)
    _sessionChange = Signal(object)

    def __init__(self, model: ChatMessageModel, runner: AsyncioRunner, parent: Any = None) -> None:
        super().__init__(parent)
        self._model = model
        self._runner = runner
        self._state = "idle"
        self._last_error = ""
        self._gateway_detail = ""
        self._gateway_channels: list[dict[str, Any]] = []
        self._configured_gateway_channels: list[str] = []
        self._enabled_gateway_channels: list[str] = []
        self._channel_errors: dict[str, str] = {}
        self._agent: Any = None
        self._channels: Any = None
        self._cron: Any = None
        self._heartbeat: Any = None
        self._background_tasks: list[asyncio.Task[Any]] = []
        self._session_key = "desktop:local"
        self._desired_session_key = self._session_key
        self._committed_session_key = self._session_key
        self._startup_target_key = ""
        self._startup_pending: list[_QueuedUiMessage] = []
        self._history_initialized = False
        self._history_fingerprint: tuple[int, str] | None = None
        self._history_cache: OrderedDict[str, _HistorySnapshot] = OrderedDict()
        self._history_loading = False
        self._active_session_ready = False
        self._active_session_has_messages = False
        self._active_summary_key = ""
        self._active_summary_message_count: int | None = None
        self._active_summary_has_messages: bool | None = None
        self._active_session_read_only = False
        self._current_nav_id = 0
        self._history_future: Any = None
        self._send_queue: queue.Queue[tuple[str, str]] = queue.Queue()
        self._processing = False
        self._lang = "en"
        self._lock = threading.Lock()
        self._cron_status: dict[str, Any] = {}
        self._session_manager: Any = None
        self._config_data: dict[str, Any] | None = None
        self._pending_notifications: list[_QueuedUiMessage] = []
        self._active_streaming_row: int = -1
        self._active_streaming_session_key: str | None = None
        self._active_send_future: Any = None
        self._active_has_content = False
        self._pending_split = False
        self._lifecycle_request_id = 0

        self._initResult.connect(self._handle_init_result)
        self._sendResult.connect(self._handle_send_result)
        self._historyResult.connect(self._handle_history_result)
        self._progressUpdate.connect(self._handle_progress_update)
        self._toolHintUpdate.connect(self._handle_tool_hint_update)
        self._systemResponse.connect(self._handle_system_response)
        self._startupMessage.connect(self._handle_startup_message)
        self._controlPlaneError.connect(self._handle_control_plane_error)
        self._sessionChange.connect(self._handle_session_change)

    # ------------------------------------------------------------------
    # Qt properties
    # ------------------------------------------------------------------

    @Property(str, notify=stateChanged)
    def state(self) -> str:
        return self._state

    @Property(str, notify=errorChanged)
    def lastError(self) -> str:
        return self._last_error

    @Property(bool, notify=errorChanged)
    def gatewayDetailIsError(self) -> bool:
        return bool(self._last_error)

    @Property(str, notify=gatewayDetailChanged)
    def gatewayDetail(self) -> str:
        return self._gateway_detail

    @Property(list, notify=gatewayChannelsChanged)
    def gatewayChannels(self) -> list[dict[str, Any]]:
        return [dict(item) for item in self._gateway_channels]

    @Property(QObject, constant=True)
    def messages(self) -> ChatMessageModel:
        return self._model

    @Property(bool, notify=historyLoadingChanged)
    def historyLoading(self) -> bool:
        return self._history_loading

    @Property(bool, notify=activeSessionStateChanged)
    def activeSessionReady(self) -> bool:
        return self._active_session_ready

    @Property(bool, notify=activeSessionStateChanged)
    def activeSessionHasMessages(self) -> bool:
        return self._active_session_has_messages

    # ------------------------------------------------------------------
    # Public slots
    # ------------------------------------------------------------------

    @Slot(str)
    def setLanguage(self, lang: str) -> None:
        self._lang = lang if lang in ("zh", "en") else "en"

    @Slot(list)
    def setConfiguredGatewayChannels(self, channels: list[str]) -> None:
        normalized = _normalize_gateway_channels(
            [
                channel.strip()
                for channel in channels
                if isinstance(channel, str) and channel.strip()
            ]
        )
        if self._configured_gateway_channels == normalized:
            return
        self._configured_gateway_channels = normalized
        if self._state in ("idle", "stopped", "starting"):
            self._refresh_gateway_channels()

    @Slot("QVariant")
    def setConfigData(self, data: object) -> None:
        self._config_data = copy.deepcopy(data) if isinstance(data, dict) else None

    @Slot()
    def start(self) -> None:
        if self._state in ("starting", "running"):
            return
        self._channel_errors.clear()
        self._clear_gateway_detail()
        self._set_state("starting")
        self._refresh_gateway_channels()
        self._runner.start()
        self._lifecycle_request_id += 1
        request_id = self._lifecycle_request_id
        self._runner.submit(self._init_gateway()).add_done_callback(
            lambda future, rid=request_id: self._on_init_done(rid, future)
        )

    @Slot()
    def stop(self) -> None:
        if self._state == "stopped":
            return
        self._channel_errors.clear()
        self._enabled_gateway_channels = []
        self._clear_gateway_detail()
        self._lifecycle_request_id += 1
        self._set_state("stopped")
        self._refresh_gateway_channels()
        if self._agent is not None:
            try:
                self._runner.submit(self._shutdown_gateway())
            except RuntimeError:
                pass
        # NOTE: Do NOT shutdown the runner here.
        # The runner is shared with SessionService for history browsing.
        # Final shutdown is handled by main.py on app exit.

    @Slot()
    def restart(self) -> None:
        self.stop()
        QTimer.singleShot(300, self.start)

    @Slot(object)
    def setSessionManager(self, sm: Any) -> None:
        """Allow history browsing before gateway starts."""
        previous = self._session_manager
        if previous is sm:
            return
        if previous is not None:
            remove_listener = getattr(previous, "remove_change_listener", None)
            if callable(remove_listener):
                try:
                    remove_listener(self._on_session_change)
                except Exception as exc:
                    logger.debug("Skip session listener removal: {}", exc)
        self._history_cache.clear()
        self._set_active_session_state(False, False)
        self._session_manager = sm
        add_listener = getattr(sm, "add_change_listener", None)
        if callable(add_listener):
            add_listener(self._on_session_change)

    @Slot(str)
    def sendMessage(self, text: str) -> None:
        if not text.strip():
            return
        if self._active_session_read_only:
            return
        row = self._model.append_user(text)
        self.messageAppended.emit(row)
        self._enqueue(text)

    @Slot(str)
    def setSessionKey(self, key: str) -> None:
        """Called when SessionService switches active session. Loads history."""
        if key == self._desired_session_key and (
            self._history_initialized or self._history_future is not None
        ):
            return
        self._cancel_history_future()
        self._current_nav_id += 1
        self._apply_session_key(key, self._current_nav_id)

    @Slot(str, object, object)
    def setSessionSummary(self, key: str, message_count: object, has_messages: object) -> None:
        self._active_summary_key = key
        self._active_summary_message_count = (
            message_count if isinstance(message_count, int) and message_count >= 0 else None
        )
        self._active_summary_has_messages = has_messages if isinstance(has_messages, bool) else None

    @Slot(bool)
    def setActiveSessionReadOnly(self, read_only: bool) -> None:
        self._active_session_read_only = bool(read_only)

    @Slot(str)
    def notifyStartupSessionReady(self, key: str) -> None:
        if not key:
            return
        self._startup_target_key = key
        self._drain_startup_pending()

    def _drain_startup_pending(self) -> None:
        if not self._startup_pending or not self._can_flush_startup_messages():
            return
        pending, self._startup_pending = self._startup_pending, []
        target_key = self._startup_target_key
        for message in pending:
            self._queue_or_show_ui_message(message.with_session_key(target_key))

    def _handle_startup_message(self, message: object) -> None:
        if not isinstance(message, DesktopStartupMessage) or not message.content:
            return
        key = self._default_startup_session_key()
        if not key:
            self._startup_pending.append(_QueuedUiMessage.from_startup(message))
            return
        self._queue_or_show_ui_message(_QueuedUiMessage.from_startup(message, session_key=key))

    def _default_startup_session_key(self) -> str:
        if self._session_key and self._session_key != "desktop:local":
            return self._session_key
        if self._startup_target_key:
            return self._startup_target_key
        return ""

    def _should_defer_startup_message(self, session_key: str) -> bool:
        if self._session_manager is None:
            return False
        target_key = session_key or self._default_startup_session_key()
        if not target_key:
            return True
        if target_key != (self._startup_target_key or self._session_key):
            return False
        return not self._can_flush_startup_messages()

    def _can_flush_startup_messages(self) -> bool:
        return bool(self._startup_target_key) and self._history_initialized

    def _on_session_change(self, event: SessionChangeEvent) -> None:
        self._sessionChange.emit(event)

    def _handle_session_change(self, event: object) -> None:
        if not isinstance(event, SessionChangeEvent):
            return
        if event.kind == "deleted":
            self._history_cache.pop(event.session_key, None)
            return
        if event.kind != "messages":
            return
        active_key = self._desired_session_key or self._committed_session_key
        if not active_key or event.session_key != active_key:
            self._history_cache.pop(event.session_key, None)
            return
        self._cancel_history_future()
        self._request_history_load(active_key, self._current_nav_id, show_loading=False)

    def _apply_session_key(self, key: str, nav_id: int) -> None:
        previous_committed = self._committed_session_key
        switched_session = previous_committed != key
        needs_seen_commit = bool(key) and (
            previous_committed != key or not self._history_initialized
        )
        cached_snapshot = self._history_cache.get(key) if key else None
        raw_tail_snapshot: list[dict[str, Any]] | None = None
        summary_knows_empty = (
            key
            and key == self._active_summary_key
            and (
                self._active_summary_message_count == 0
                or self._active_summary_has_messages is False
            )
        )
        if cached_snapshot is not None and key:
            self._history_cache.move_to_end(key)
        elif self._session_manager is not None and key and not summary_knows_empty:
            peek_tail_messages = getattr(self._session_manager, "peek_tail_messages", None)
            if callable(peek_tail_messages):
                try:
                    tail_messages_obj: object = peek_tail_messages(key, _HISTORY_FULL_LIMIT)
                    if isinstance(tail_messages_obj, list):
                        next_tail_snapshot: list[dict[str, Any]] = []
                        for message in tail_messages_obj:
                            if isinstance(message, dict):
                                next_tail_snapshot.append(dict(message))
                        raw_tail_snapshot = next_tail_snapshot
                except Exception:
                    raw_tail_snapshot = None
        self._desired_session_key = key
        self._committed_session_key = key
        self._session_key = key
        if _DEBUG_SWITCH:
            logger.debug(
                "switch_request desired={} committed={} nav_id={}",
                self._desired_session_key,
                self._committed_session_key,
                nav_id,
            )

        if previous_committed != key:
            self._active_streaming_row = -1
            self._active_has_content = False
            self._pending_split = False

        if self._session_manager is not None and needs_seen_commit:
            self._mark_session_seen_ai(key)

        if self._session_manager is None or not key:
            self._set_history_loading(False)
            self._history_initialized = False
            self._history_fingerprint = None
            self._set_active_session_state(False, False)
            self._model.clear()
            self._emit_session_view_applied(key, switched_session=switched_session)
            return

        if cached_snapshot is None and raw_tail_snapshot is None:
            if summary_knows_empty:
                fingerprint = self._history_signature([])
                self._history_initialized = True
                self._history_fingerprint = fingerprint
                self._set_active_session_state(True, False)
                self._cache_history_snapshot(key, fingerprint, [], False)
                self._model.clear()
                self._set_history_loading(False)
                self._emit_session_view_applied(key, switched_session=switched_session)
                self._request_history_load(key, nav_id, show_loading=False)
                return
            self._history_initialized = False
            self._history_fingerprint = None
            self._set_active_session_state(False, False)
            self._model.clear()
        elif cached_snapshot is None:
            prepared_messages = ChatMessageModel.prepare_history(raw_tail_snapshot or [])
            fingerprint = self._history_signature(prepared_messages)
            has_messages = bool(raw_tail_snapshot)
            self._history_initialized = True
            self._history_fingerprint = fingerprint
            self._set_active_session_state(True, has_messages)
            self._cache_history_snapshot(key, fingerprint, prepared_messages, has_messages)
            self._model.load_prepared([dict(msg) for msg in prepared_messages])
        else:
            self._history_initialized = True
            self._history_fingerprint = cached_snapshot.fingerprint
            self._set_active_session_state(True, cached_snapshot.has_messages)
            self._model.load_prepared([dict(msg) for msg in cached_snapshot.prepared_messages])

        self._emit_session_view_applied(key, switched_session=switched_session)

        self._request_history_load(
            key,
            nav_id,
            show_loading=(cached_snapshot is None and raw_tail_snapshot is None),
        )

    def _request_history_load(
        self, key: str, nav_id: int, *, show_loading: bool | None = None
    ) -> None:
        if show_loading is None:
            show_loading = not self._history_initialized
        if show_loading:
            self._set_history_loading(True)
        if _DEBUG_SWITCH:
            logger.debug("history_load key={} nav_id={}", key, nav_id)
        fut = self._runner.submit(self._load_history(key, nav_id, _HISTORY_FULL_LIMIT))
        self._history_future = fut
        fut.add_done_callback(self._on_history_done)

    async def _load_history(
        self, key: str, nav_id: int, limit: int
    ) -> tuple[str, int, tuple[int, str], list[dict[str, Any]], bool]:
        """Load session message history from SessionManager (runs on asyncio thread)."""
        import time

        t0 = time.perf_counter() if _PROFILE else 0
        sm = self._session_manager

        def _read_raw_messages() -> list[dict[str, Any]]:
            try:
                result = sm.get_tail_messages(key, limit)
                if isinstance(result, list):
                    return result
                raise TypeError("tail_messages_not_list")
            except Exception:
                session = sm.get_or_create(key)
                try:
                    fallback = session.get_display_history()
                except Exception:
                    fallback = None
                if not isinstance(fallback, list):
                    fallback = session.get_history() if hasattr(session, "get_history") else []
                if limit > 0:
                    fallback = fallback[-limit:]
                return fallback

        raw_messages: list[dict[str, Any]] = await self._run_user_io(_read_raw_messages)
        t1 = time.perf_counter() if _PROFILE else 0
        if _PROFILE:
            logger.debug("📊 History load: read_raw={:.3f}s", t1 - t0)
        prepared_messages = await self._run_user_io(ChatMessageModel.prepare_history, raw_messages)
        fingerprint = self._history_signature(prepared_messages)
        t_end = time.perf_counter() if _PROFILE else 0
        if _PROFILE:
            logger.debug("📊 History prepare: {:.3f}s", t_end - t1)
        return key, nav_id, fingerprint, prepared_messages, bool(raw_messages)

    def _on_history_done(self, future: Any) -> None:
        """Runs on asyncio thread — only emits signal."""
        if future is not self._history_future:
            return
        self._history_future = None
        if future.cancelled():
            return
        exc = future.exception()
        if exc:
            self._historyResult.emit(False, str(exc), None)
        else:
            self._historyResult.emit(True, "", future.result())

    def _handle_history_result(self, ok: bool, error: str, messages: Any) -> None:
        """Runs on Qt main thread — fills ChatMessageModel with history."""
        if not ok:
            self._set_history_loading(False)
            return
        loaded_key = self._session_key
        loaded_nav_id = 0
        loaded_messages = messages or []
        loaded_fingerprint: tuple[int, str] | None = None
        loaded_has_messages = False
        loaded_prepared = False
        if isinstance(messages, tuple) and len(messages) == 5:
            (
                loaded_key,
                loaded_nav_id,
                loaded_fingerprint,
                loaded_messages,
                loaded_has_messages,
            ) = messages
            loaded_messages = loaded_messages or []
            loaded_prepared = True
        elif isinstance(messages, tuple) and len(messages) == 4:
            loaded_key, loaded_nav_id, loaded_fingerprint, loaded_messages = messages
            loaded_messages = loaded_messages or []
            loaded_has_messages = bool(loaded_messages)
            loaded_prepared = True
        elif isinstance(messages, tuple) and len(messages) == 3:
            loaded_key, loaded_nav_id, loaded_messages = messages
            loaded_messages = loaded_messages or []
            loaded_has_messages = bool(loaded_messages)
        elif isinstance(messages, tuple) and len(messages) == 2:
            loaded_key, loaded_messages = messages
            loaded_messages = loaded_messages or []
            loaded_has_messages = bool(loaded_messages)
        if loaded_nav_id and loaded_nav_id != self._current_nav_id:
            if _DEBUG_SWITCH:
                logger.debug(
                    "history_gating loaded_nav_id={} current_nav_id={}",
                    loaded_nav_id,
                    self._current_nav_id,
                )
            return
        if loaded_key != self._desired_session_key:
            return
        fingerprint = loaded_fingerprint or self._history_signature(loaded_messages)
        if self._history_initialized and fingerprint == self._history_fingerprint:
            self._set_history_loading(False)
            return
        self._history_initialized = True
        self._history_fingerprint = fingerprint
        self._committed_session_key = loaded_key
        self._session_key = loaded_key
        self._set_active_session_state(True, loaded_has_messages)
        if loaded_prepared:
            prepared_messages = [dict(msg) for msg in loaded_messages]
            self._cache_history_snapshot(
                loaded_key, fingerprint, prepared_messages, loaded_has_messages
            )
            preserve_transient_tail = (
                self._processing and loaded_key == self._active_streaming_session_key
            )
            previous_active_row = self._active_streaming_row
            self._model.load_prepared(
                prepared_messages, preserve_transient_tail=preserve_transient_tail
            )
            if loaded_key == self._active_streaming_session_key:
                rebound_row = self._rebind_active_streaming_row_after_history()
                active_message = self._model.message_at(rebound_row)
                if active_message is not None:
                    if self._pending_split and (
                        rebound_row != previous_active_row
                        or active_message.get("status") != "typing"
                    ):
                        self._pending_split = False
                else:
                    self._active_has_content = False
                    self._pending_split = False
        else:
            self._model.load_history(loaded_messages)
        if _DEBUG_SWITCH:
            logger.debug(
                "history_applied key={} rows={} nav_id={}",
                loaded_key,
                self._model.rowCount(),
                loaded_nav_id,
            )
        self._set_history_loading(False)
        if loaded_key == self._startup_target_key:
            self._drain_startup_pending()

    @staticmethod
    def _history_signature(messages: list[dict[str, Any]]) -> tuple[int, str]:
        if not messages:
            return (0, "")
        return (len(messages), repr(messages))

    def _set_active_session_state(self, ready: bool, has_messages: bool) -> None:
        if (
            self._active_session_ready == ready
            and self._active_session_has_messages == has_messages
        ):
            return
        self._active_session_ready = ready
        self._active_session_has_messages = has_messages
        self.activeSessionStateChanged.emit()

    def _emit_session_view_applied(self, key: str, *, switched_session: bool) -> None:
        if not switched_session:
            return
        self.sessionViewApplied.emit(key)

    def _cache_history_snapshot(
        self,
        key: str,
        fingerprint: tuple[int, str],
        prepared_messages: list[dict[str, Any]],
        has_messages: bool,
    ) -> None:
        if not key:
            return
        self._history_cache[key] = _HistorySnapshot(
            fingerprint=fingerprint,
            prepared_messages=[dict(msg) for msg in prepared_messages],
            has_messages=has_messages,
        )
        self._history_cache.move_to_end(key)
        while len(self._history_cache) > _HISTORY_CACHE_LIMIT:
            self._history_cache.popitem(last=False)

    # ------------------------------------------------------------------
    # Internal: full gateway init (mirrors CLI run_gateway)
    # ------------------------------------------------------------------

    async def _init_gateway(self) -> tuple[Any, list[str]]:
        """Initialize full gateway stack. Returns (session_manager, enabled_channels)."""
        from bao.config.loader import ensure_first_run, get_config_path, load_config
        from bao.config.schema import Config
        from bao.gateway.builder import build_gateway_stack, send_startup_greeting
        from bao.providers import make_provider

        # --- config ---
        ensure_first_run()
        config_path = get_config_path()
        if self._config_data is not None:
            config = Config.model_validate(copy.deepcopy(self._config_data))
        else:
            try:
                config = load_config(config_path)
            except SystemExit as exc:
                raise RuntimeError(f"Config unavailable at {config_path}") from exc

        # --- build shared gateway stack ---
        provider = make_provider(config)
        reuse_sm = None
        try:
            existing = self._session_manager
            if existing is not None:
                existing_ws = getattr(existing, "workspace", None)
                if existing_ws and str(Path(str(existing_ws)).expanduser()) == str(
                    Path(str(config.workspace_path)).expanduser()
                ):
                    reuse_sm = existing
        except Exception:
            reuse_sm = None
        stack = build_gateway_stack(
            config,
            provider,
            reuse_sm,
            on_channel_error=self._handle_channel_error,
        )

        # Store references for shutdown
        self._agent = stack.agent
        self._channels = stack.channels
        self._cron = stack.cron
        self._heartbeat = stack.heartbeat

        # --- start background services on the asyncio loop ---
        loop = asyncio.get_running_loop()
        await stack.cron.start()
        await stack.heartbeat.start()
        self._cron_status = stack.cron.status()
        self._background_tasks = [
            loop.create_task(stack.agent.run()),
            loop.create_task(stack.channels.start_all()),
            loop.create_task(
                send_startup_greeting(
                    stack.agent,
                    stack.bus,
                    stack.config,
                    on_desktop_startup_message=lambda msg: self._startupMessage.emit(msg),
                    channels=stack.channels,
                )
            ),
        ]

        return stack.session_manager, stack.channels.enabled_channels

    def _handle_channel_error(self, stage: str, name: str, detail: str) -> None:
        error_message = self._format_channel_error(stage, name, detail)
        self._channel_errors[name] = detail
        self._refresh_gateway_channels()
        self._controlPlaneError.emit(error_message)

    def _handle_control_plane_error(self, message: str) -> None:
        self._set_gateway_detail(message, error=message)

    def _format_channel_error(self, stage: str, name: str, detail: str) -> str:
        is_zh = self._lang == "zh"
        zh_label, en_label = _CHANNEL_ERROR_LABELS.get(stage, ("通道错误", "Channel error"))
        prefix = zh_label if is_zh else en_label
        return f"⚠ {prefix}: {name}: {detail}"

    def _on_init_done(self, request_id: int, future: Any) -> None:
        """Runs on asyncio thread — only emits signal."""
        exc = future.exception()
        if exc:
            self._initResult.emit(request_id, False, f"Gateway init failed: {exc}", None, [])
        else:
            sm, ch_list = future.result()
            self._initResult.emit(request_id, True, "", sm, ch_list)

    def _handle_init_result(
        self, request_id: int, ok: bool, error_msg: str, session_manager: Any, channels: list[str]
    ) -> None:
        """Runs on Qt main thread."""
        if request_id != self._lifecycle_request_id:
            return
        if not ok:
            self._set_error(error_msg)
            return
        self._set_state("running")
        self._enabled_gateway_channels = _normalize_gateway_channels(channels)
        self._refresh_gateway_channels()
        # Build localized status message
        is_zh = self._lang == "zh"
        parts = ["✓ 网关已启动" if is_zh else "✓ Gateway started"]
        if channels:
            lbl = "通道" if is_zh else "channels"
            parts.append(f"{lbl}: {', '.join(channels)}")
        cron_jobs = self._cron_status.get("jobs", 0)
        if cron_jobs > 0:
            lbl = "定时任务" if is_zh else "cron"
            parts.append(f"{lbl}: {cron_jobs} {'个' if is_zh else 'jobs'}")
        hb = "心跳: 每 30 分钟" if is_zh else "heartbeat: every 30m"
        parts.append(hb)
        self.setSessionManager(session_manager)
        if not self._last_error:
            self._set_gateway_summary(" — ".join(parts))
        self.gatewayReady.emit(session_manager, channels)
        self._drain_queue()

    # ------------------------------------------------------------------
    # Internal: message queue (serial)
    # ------------------------------------------------------------------

    def _enqueue(self, text: str) -> None:
        self._send_queue.put((self._session_key, text))
        if self._state == "running":
            self._drain_queue()

    def _drain_queue(self) -> None:
        with self._lock:
            if self._processing:
                return
            try:
                session_key, text = self._send_queue.get_nowait()
            except queue.Empty:
                return
            self._processing = True

        self._set_session_running(session_key, True)

        assistant_row = self._append_typing_row()
        self._active_streaming_row = assistant_row
        self._active_streaming_session_key = session_key
        self._active_has_content = False
        self._pending_split = False

        fut = self._runner.submit(self._call_agent(text, session_key))
        self._active_send_future = fut
        fut.add_done_callback(lambda f: self._on_send_done(f, assistant_row))

    def _on_send_done(self, future: Any, row: int) -> None:
        """Runs on asyncio thread — only emits signal."""
        if future.cancelled():
            self._sendResult.emit(row, False, "Cancelled.")
            return
        exc = future.exception()
        if exc:
            self._sendResult.emit(row, False, f"Error: {exc}")
        else:
            self._sendResult.emit(row, True, future.result() or "")

    def _handle_send_result(self, _row: int, ok: bool, content: str) -> None:
        """Runs on Qt main thread. Finalizes the active streaming bubble."""
        self._active_send_future = None
        is_provider_error = ok and isinstance(content, str) and content.startswith("Error calling ")
        final_status = "error" if (not ok or is_provider_error) else "done"
        should_render_in_ui = self._should_render_active_stream()
        active = self._active_streaming_row
        if active < 0 and should_render_in_ui:
            active = self._restore_active_streaming_row(emit_append_signal=True)
        if (
            ok
            and not is_provider_error
            and self._pending_split
            and self._active_has_content
            and content
        ):
            if active >= 0:
                self._model.set_status(active, "done")
                active = self._append_typing_row()
                self._active_streaming_row = active
                self._active_has_content = False
        if not ok:
            if active >= 0:
                self._model.set_format(active, "plain")
                self._model.update_content(active, content)
                self.contentUpdated.emit(active, content)
                self._model.set_status(active, "error")
        else:
            if content:
                if active >= 0:
                    if is_provider_error:
                        self._model.set_format(active, "plain")
                    self._model.update_content(active, content)
                    self.contentUpdated.emit(active, content)
                self._active_has_content = active >= 0
            if active >= 0:
                self._model.set_status(active, "error" if is_provider_error else "done")
        completed_session_key = self._active_streaming_session_key
        self._active_streaming_row = -1
        self._active_streaming_session_key = None
        self._active_has_content = False
        self._pending_split = False
        should_mark_seen = (
            ok
            and not is_provider_error
            and completed_session_key
            and completed_session_key == self._committed_session_key
        )
        if completed_session_key and not should_mark_seen:
            self._set_session_running(completed_session_key, False)
        completed_key = completed_session_key if isinstance(completed_session_key, str) else ""
        if should_mark_seen and completed_key:
            self._mark_session_seen_ai(
                completed_key,
                emit_change=True,
                extra_updates={"session_running": False},
            )
        self.statusUpdated.emit(active, final_status)
        # Drain pending system responses before releasing lock
        pending: list[_QueuedUiMessage] = []
        with self._lock:
            self._processing = False
            pending = self._pending_notifications[:]
            self._pending_notifications.clear()
        for message in pending:
            self._show_ui_message(message)

    async def _call_agent(self, text: str, session_key: str) -> str:
        if self._agent is None:
            raise RuntimeError("Agent not initialized")

        from bao.agent.protocol import StreamEventType
        from bao.providers.retry import PROGRESS_RESET

        accumulated = ""

        async def _on_progress(delta: str) -> None:
            nonlocal accumulated
            if delta == PROGRESS_RESET:
                self._progressUpdate.emit(-2, "")
                accumulated = ""
                return
            accumulated += delta
            self._progressUpdate.emit(-1, accumulated)

        async def _on_event(event: Any) -> None:
            if getattr(event, "type", "") == StreamEventType.TOOL_HINT:
                hint_text = getattr(event, "text", "")
                if isinstance(hint_text, str) and hint_text.strip() and self._tool_hints_enabled():
                    self._toolHintUpdate.emit(hint_text)

        result = await self._agent.process_direct(
            text,
            session_key=session_key,
            channel="desktop",
            chat_id="local",
            on_progress=_on_progress,
            on_event=_on_event,
        )
        return result

    def _handle_progress_update(self, row: int, content: str) -> None:
        """Runs on Qt main thread. Routes streaming content to active bubble."""
        should_render_in_ui = self._should_render_active_stream()
        if row == -2:
            self._pending_split = True
            return
        if row == -1 and self._pending_split:
            if self._active_has_content:
                cur = self._active_streaming_row
                if cur >= 0 and should_render_in_ui:
                    self._model.set_status(cur, "done")
                if should_render_in_ui:
                    new_row = self._append_typing_row()
                    self._active_streaming_row = new_row
                else:
                    self._active_streaming_row = -1
                self._active_has_content = False
            self._pending_split = False
        if row == -1 and should_render_in_ui and self._active_streaming_row < 0:
            self._restore_active_streaming_row(emit_append_signal=True)
        target = self._active_streaming_row if row == -1 else row
        if target >= 0 and should_render_in_ui:
            self._model.update_content(target, content)
            self.contentUpdated.emit(target, content)
        self._active_has_content = bool(content)

    def _restore_active_streaming_row(self, *, emit_append_signal: bool) -> int:
        if not self._should_render_active_stream():
            return -1

        last_row = self._model.rowCount() - 1
        last_message = self._model.message_at(last_row)
        if last_message is not None and last_message.get("role") == "assistant":
            self._active_streaming_row = last_row
            self._active_has_content = bool(last_message.get("content"))
            return last_row

        new_row = (
            self._append_typing_row()
            if emit_append_signal
            else self._model.append_assistant("", status="typing")
        )
        self._active_streaming_row = new_row
        self._active_has_content = False
        return new_row

    def _rebind_active_streaming_row_after_history(self) -> int:
        if not self._should_render_active_stream():
            self._active_streaming_row = -1
            self._active_has_content = False
            return -1

        last_row = self._model.rowCount() - 1
        last_message = self._model.message_at(last_row)
        if last_message is not None and last_message.get("role") == "assistant":
            if last_message.get("_source") == "assistant-progress":
                new_row = self._append_typing_row()
                self._active_streaming_row = new_row
                self._active_has_content = False
                return new_row
            self._active_streaming_row = last_row
            self._active_has_content = bool(last_message.get("content"))
            return last_row

        new_row = self._append_typing_row()
        self._active_streaming_row = new_row
        self._active_has_content = False
        return new_row

    def _append_typing_row(self) -> int:
        row = self._model.append_assistant("", status="typing")
        self.messageAppended.emit(row)
        return row

    def _handle_tool_hint_update(self, hint: str) -> None:
        should_render_in_ui = self._should_render_active_stream()
        if self._active_streaming_row < 0 and should_render_in_ui:
            self._restore_active_streaming_row(emit_append_signal=True)
        if self._active_streaming_row < 0:
            return
        current_row = self._active_streaming_row
        if self._active_has_content:
            if should_render_in_ui:
                self._model.set_status(current_row, "done")
                new_row = self._append_typing_row()
                self._active_streaming_row = new_row
                current_row = new_row
            else:
                self._active_streaming_row = -1
                self._active_has_content = False
                return
        clean_hint = hint.strip()
        if should_render_in_ui and clean_hint:
            self._model.update_content(current_row, clean_hint)
            self.contentUpdated.emit(current_row, clean_hint)
            self._model.set_status(current_row, "done")
            next_row = self._append_typing_row()
            self._active_streaming_row = next_row
            self._active_has_content = False
        else:
            self._active_streaming_row = -1
            self._active_has_content = False
        self._pending_split = False

    def _tool_hints_enabled(self) -> bool:
        data = self._config_data or {}
        agents = data.get("agents") if isinstance(data, dict) else None
        defaults = agents.get("defaults") if isinstance(agents, dict) else None
        if not isinstance(defaults, dict):
            return True
        value = defaults.get("sendToolHints", defaults.get("send_tool_hints", True))
        return value if isinstance(value, bool) else True

    def _handle_system_response(self, content: str, session_key: str = "") -> None:
        """Runs on Qt main thread. Queue if streaming, else show immediately."""
        self._queue_or_show_ui_message(
            _QueuedUiMessage(
                role="system",
                content=content,
                session_key=session_key,
                entrance_style="system",
            )
        )

    def _queue_or_show_ui_message(self, message: _QueuedUiMessage) -> None:
        if not message.content:
            return
        if self._should_defer_startup_message(message.session_key):
            self._startup_pending.append(message)
            return
        target_session_key = (
            message.session_key or self._default_startup_session_key() or self._session_key
        )
        queued = message.with_session_key(target_session_key)
        with self._lock:
            if self._processing:
                self._pending_notifications.append(queued)
                return
        self._show_ui_message(queued)

    def _show_ui_message(self, message: _QueuedUiMessage) -> None:
        if message.role == "assistant":
            self._show_assistant_response(message.content, session_key=message.session_key)
            return
        self._show_system_response(
            message.content,
            entrance_style=message.entrance_style,
            session_key=message.session_key,
        )

    def _show_system_response(
        self,
        content: str,
        *,
        entrance_style: str = "system",
        session_key: str = "",
    ) -> None:
        target_session_key = session_key or self._session_key
        self._append_transient_system_message(
            content,
            status="done",
            entrance_style=entrance_style,
            session_key=target_session_key,
            show_in_ui=self._should_show_startup_message(target_session_key),
        )

    def _show_assistant_response(self, content: str, *, session_key: str = "") -> None:
        target_session_key = session_key or self._session_key
        self._append_transient_assistant_message(
            content,
            status="done",
            session_key=target_session_key,
            show_in_ui=self._should_show_startup_message(target_session_key),
        )

    def _should_show_startup_message(self, target_session_key: str) -> bool:
        if target_session_key == self._session_key:
            return True
        return (
            self._session_key == "desktop:local"
            and bool(self._startup_target_key)
            and target_session_key == self._startup_target_key
        )

    def _append_transient_system_message(
        self,
        content: str,
        *,
        status: str = "done",
        entrance_style: str = "system",
        session_key: str = "",
        show_in_ui: bool = True,
    ) -> None:
        if not content:
            return
        target_session_key = session_key or self._session_key
        self._schedule_system_message_persist(target_session_key, content, status, entrance_style)
        if not show_in_ui:
            return
        row = self._model.append_system(
            content,
            status=status,
            entrance_style=entrance_style,
            entrance_pending=True,
        )
        self.messageAppended.emit(row)

    def _append_transient_assistant_message(
        self,
        content: str,
        *,
        status: str = "done",
        session_key: str = "",
        show_in_ui: bool = True,
    ) -> None:
        if not content:
            return
        target_session_key = session_key or self._session_key
        is_visible_active_session = show_in_ui and target_session_key == self._committed_session_key
        self._schedule_assistant_message_persist(
            target_session_key,
            content,
            status,
            mark_seen=is_visible_active_session,
        )
        if not show_in_ui:
            return
        row = self._model.append_assistant(
            content,
            status=status,
            entrance_style="assistantReceived",
            entrance_pending=True,
        )
        self.messageAppended.emit(row)

    @staticmethod
    def _persist_system_message_with_manager(
        session_manager: Any,
        session_key: str,
        content: str,
        status: str,
        entrance_style: str,
    ) -> None:
        session = session_manager.get_or_create(session_key)
        session.add_message(
            "user",
            content,
            status=status,
            _source="desktop-system",
            entrance_style=entrance_style,
        )
        session_manager.save(session, emit_change=False)

    async def _persist_system_message_async(
        self,
        session_manager: Any,
        session_key: str,
        content: str,
        status: str,
        entrance_style: str,
    ) -> None:
        await self._run_bg_io(
            self._persist_system_message_with_manager,
            session_manager,
            session_key,
            content,
            status,
            entrance_style,
        )

    def _on_system_persist_done(self, future: Any) -> None:
        try:
            future.result()
        except Exception as exc:
            logger.warning("Failed to persist desktop system message: {}", exc)

    @staticmethod
    def _persist_assistant_message_with_manager(
        session_manager: Any,
        session_key: str,
        content: str,
        status: str,
    ) -> None:
        session = session_manager.get_or_create(session_key)
        session.add_message("assistant", content, status=status, format="markdown")
        session_manager.save(session, emit_change=False)

    async def _persist_assistant_message_async(
        self,
        session_manager: Any,
        session_key: str,
        content: str,
        status: str,
    ) -> None:
        await self._run_bg_io(
            self._persist_assistant_message_with_manager,
            session_manager,
            session_key,
            content,
            status,
        )

    def _on_assistant_persist_done(
        self,
        future: Any,
        *,
        session_key: str = "",
        mark_seen: bool = False,
    ) -> None:
        try:
            future.result()
        except Exception as exc:
            logger.warning("Failed to persist desktop startup assistant message: {}", exc)
            return
        if mark_seen and session_key:
            self._mark_session_seen_ai(session_key)

    def _schedule_system_message_persist(
        self,
        session_key: str,
        content: str,
        status: str,
        entrance_style: str,
    ) -> None:
        session_manager = self._session_manager
        if session_manager is None:
            return

        if isinstance(self._runner, AsyncioRunner):
            try:
                future = self._runner.submit(
                    self._persist_system_message_async(
                        session_manager, session_key, content, status, entrance_style
                    )
                )
                future.add_done_callback(self._on_system_persist_done)
                return
            except RuntimeError:
                pass

        try:
            self._persist_system_message_with_manager(
                session_manager,
                session_key,
                content,
                status,
                entrance_style,
            )
        except Exception as exc:
            logger.warning("Failed to persist desktop system message: {}", exc)

    def _schedule_assistant_message_persist(
        self,
        session_key: str,
        content: str,
        status: str,
        *,
        mark_seen: bool = False,
    ) -> None:
        session_manager = self._session_manager
        if session_manager is None:
            return

        if isinstance(self._runner, AsyncioRunner):
            try:
                future = self._runner.submit(
                    self._persist_assistant_message_async(
                        session_manager, session_key, content, status
                    )
                )
                future.add_done_callback(
                    lambda done, key=session_key, should_mark=mark_seen: (
                        self._on_assistant_persist_done(
                            done,
                            session_key=key,
                            mark_seen=should_mark,
                        )
                    )
                )
                return
            except RuntimeError:
                pass

        try:
            self._persist_assistant_message_with_manager(
                session_manager, session_key, content, status
            )
        except Exception as exc:
            logger.warning("Failed to persist desktop startup assistant message: {}", exc)
            return
        if mark_seen:
            self._mark_session_seen_ai(session_key)

    def _should_render_active_stream(self) -> bool:
        return self._active_streaming_session_key in (None, self._committed_session_key)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _set_state(self, state: str) -> None:
        if self._state != state:
            self._state = state
            self.stateChanged.emit(state)
            self._refresh_gateway_channels()

    def _cancel_history_future(self) -> None:
        future = self._history_future
        self._history_future = None
        if future is None:
            return
        try:
            future.cancel()
        except Exception:
            pass

    async def _run_user_io(self, fn: Any, *args: Any) -> Any:
        if isinstance(self._runner, AsyncioRunner):
            return await self._runner.run_user_io(fn, *args)
        return await asyncio.to_thread(fn, *args)

    async def _run_bg_io(self, fn: Any, *args: Any) -> Any:
        if isinstance(self._runner, AsyncioRunner):
            return await self._runner.run_bg_io(fn, *args)
        return await asyncio.to_thread(fn, *args)

    def _set_history_loading(self, loading: bool) -> None:
        if self._history_loading != loading:
            self._history_loading = loading
            if _DEBUG_SWITCH:
                logger.debug(
                    "history_loading key={} desired={} loading={} rows={}",
                    self._session_key,
                    self._desired_session_key,
                    loading,
                    self._model.rowCount(),
                )
            self.historyLoadingChanged.emit(loading)

    def _set_error(self, msg: str) -> None:
        msg = msg.strip()
        self._set_gateway_detail(msg, error=msg)
        self._set_state("error")

    def _set_gateway_detail(self, detail: str, *, error: str = "") -> None:
        detail = detail.strip()
        error = error.strip()
        detail_changed = self._gateway_detail != detail
        error_changed = self._last_error != error
        if not detail_changed and not error_changed:
            return

        self._gateway_detail = detail
        self._last_error = error
        if error_changed:
            self.errorChanged.emit(error)
        if detail_changed:
            self.gatewayDetailChanged.emit(detail)

    def _set_gateway_summary(self, summary: str) -> None:
        self._set_gateway_detail(summary)

    def _clear_gateway_detail(self) -> None:
        self._set_gateway_detail("")

    def _refresh_gateway_channels(self) -> None:
        channels = self._build_gateway_channels_projection()
        if self._gateway_channels == channels:
            return
        self._gateway_channels = channels
        self.gatewayChannelsChanged.emit()

    def _update_session_metadata(
        self,
        key: str,
        payload: dict[str, Any],
        *,
        emit_change: bool,
    ) -> None:
        if not key or self._session_manager is None or not isinstance(payload, dict) or not payload:
            return

        session_manager = self._session_manager
        update_fn = getattr(session_manager, "update_metadata_only", None)
        if not callable(update_fn):
            return

        if isinstance(self._runner, AsyncioRunner):
            try:
                future = self._runner.submit(
                    self._run_bg_io(lambda: update_fn(key, payload, emit_change=emit_change))
                )
                future.add_done_callback(self._on_metadata_update_done)
                return
            except RuntimeError:
                pass
            except Exception as exc:
                logger.debug("Skip metadata update {}: {}", key, exc)

        try:
            update_fn(key, payload, emit_change=emit_change)
        except Exception as exc:
            logger.debug("Skip metadata update {}: {}", key, exc)

    def _set_session_running(self, key: str, is_running: bool) -> None:
        self._update_session_metadata(
            key,
            {"session_running": bool(is_running)},
            emit_change=True,
        )

    def _build_gateway_channels_projection(self) -> list[dict[str, Any]]:
        base_channels = self._enabled_gateway_channels or self._configured_gateway_channels
        ordered = _normalize_gateway_channels(base_channels + list(self._channel_errors.keys()))
        if not ordered:
            return []

        if self._state in ("idle", "stopped", "error"):
            default_state = "idle"
        elif self._state == "starting":
            default_state = "starting"
        else:
            default_state = "running"

        projection: list[dict[str, Any]] = []
        for channel in ordered:
            detail = self._channel_errors.get(channel, "")
            state = "error" if detail else default_state
            projection.append({"channel": channel, "state": state, "detail": detail})
        return projection

    def _mark_session_seen_ai(
        self,
        key: str,
        *,
        emit_change: bool = False,
        extra_updates: dict[str, Any] | None = None,
    ) -> None:
        payload: dict[str, Any] = {"desktop_last_seen_ai_at": datetime.now().isoformat()}
        if isinstance(extra_updates, dict):
            payload.update(extra_updates)
        self._update_session_metadata(key, payload, emit_change=emit_change)

    @staticmethod
    def _on_metadata_update_done(future: Any) -> None:
        try:
            future.result()
        except Exception as exc:
            logger.debug("Skip metadata update: {}", exc)

    async def _shutdown_gateway(self) -> None:
        """Full shutdown mirroring CLI finally block."""
        self._cancel_history_future()
        for t in self._background_tasks:
            t.cancel()
        if self._agent:
            await self._agent.close_mcp()
        if self._heartbeat:
            self._heartbeat.stop()
        if self._cron:
            self._cron.stop()
        if self._agent:
            self._agent.stop()
        if self._channels:
            await self._channels.stop_all()

    def handle_session_deleted(self, key: str, success: bool, _error: str) -> None:
        """Handle session deletion - cancel streaming if needed."""
        if not success:
            return
        if key == self._active_streaming_session_key and self._active_send_future:
            try:
                self._active_send_future.cancel()
            except Exception:
                pass
