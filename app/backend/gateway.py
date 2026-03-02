"""ChatService — embedded Bao gateway lifecycle + serial message queue.

State machine: idle -> starting -> running -> stopped / error

Full gateway: AgentLoop + ChannelManager + CronService + HeartbeatService,
functionally equivalent to the CLI ``bao`` command.
All Bao core calls happen on the asyncio thread via AsyncioRunner.
Internal signals marshal results back to the Qt main thread.
"""

from __future__ import annotations

import asyncio
import queue
import threading
from typing import Any

from PySide6.QtCore import Property, QObject, QTimer, Signal, Slot

from app.backend.asyncio_runner import AsyncioRunner
from app.backend.chat import ChatMessageModel


class ChatService(QObject):
    stateChanged = Signal(str)
    errorChanged = Signal(str)
    messageAppended = Signal(int)
    contentUpdated = Signal(int, str)
    statusUpdated = Signal(int, str)
    gatewayReady = Signal(object, list)  # session_manager, enabled_channels
    historyLoadingChanged = Signal(bool)

    # Internal signals: asyncio thread → Qt main thread marshaling
    _initResult = Signal(bool, str, object, list)  # ok, err, session_mgr, channels
    _sendResult = Signal(int, bool, str)  # row, ok, content_or_error
    _historyResult = Signal(bool, str, object)  # ok, error, messages_list
    _progressUpdate = Signal(int, str)  # row, accumulated_content (asyncio → Qt)
    _systemResponse = Signal(str)  # subagent completion content (asyncio → Qt)

    def __init__(self, model: ChatMessageModel, runner: AsyncioRunner, parent: Any = None) -> None:
        super().__init__(parent)
        self._model = model
        self._runner = runner
        self._state = "idle"
        self._last_error = ""
        self._agent: Any = None
        self._channels: Any = None
        self._cron: Any = None
        self._heartbeat: Any = None
        self._background_tasks: list[asyncio.Task[Any]] = []
        self._session_key = "desktop:local"
        self._history_initialized = False
        self._history_fingerprint: tuple[int, str] | None = None
        self._history_loading = False
        self._pending_session_key: str | None = None
        self._pending_history_refresh = False
        self._history_request_seq = 0
        self._history_latest_seq = 0
        self._send_queue: queue.Queue[str] = queue.Queue()
        self._processing = False
        self._lang = "en"
        self._lock = threading.Lock()
        self._cron_status: dict[str, Any] = {}
        self._session_manager: Any = None
        self._pending_system: list[str] = []
        self._active_streaming_row: int = -1
        self._active_has_content = False
        self._pending_split = False

        self._initResult.connect(self._handle_init_result)
        self._sendResult.connect(self._handle_send_result)
        self._historyResult.connect(self._handle_history_result)
        self._progressUpdate.connect(self._handle_progress_update)
        self._systemResponse.connect(self._handle_system_response)

        self._history_sync_timer = QTimer(self)
        self._history_sync_timer.setInterval(1200)
        self._history_sync_timer.timeout.connect(self._sync_active_history)
        self._history_sync_timer.start()

    # ------------------------------------------------------------------
    # Qt properties
    # ------------------------------------------------------------------

    @Property(str, notify=stateChanged)
    def state(self) -> str:
        return self._state

    @Property(str, notify=errorChanged)
    def lastError(self) -> str:
        return self._last_error

    @Property(QObject, constant=True)
    def messages(self) -> ChatMessageModel:
        return self._model

    @Property(bool, notify=historyLoadingChanged)
    def historyLoading(self) -> bool:
        return self._history_loading

    # ------------------------------------------------------------------
    # Public slots
    # ------------------------------------------------------------------

    @Slot(str)
    def setLanguage(self, lang: str) -> None:
        self._lang = lang if lang in ("zh", "en") else "en"

    @Slot()
    def start(self) -> None:
        if self._state in ("starting", "running"):
            return
        self._set_state("starting")
        self._runner.start()
        self._runner.submit(self._init_gateway()).add_done_callback(self._on_init_done)

    @Slot()
    def stop(self) -> None:
        if self._state == "stopped":
            return
        self._set_state("stopped")
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
        if self._session_manager is None:
            self._session_manager = sm

    @Slot(str)
    def sendMessage(self, text: str) -> None:
        if not text.strip():
            return
        row = self._model.append_user(text)
        self.messageAppended.emit(row)
        self._enqueue(text)

    @Slot(str)
    def setSessionKey(self, key: str) -> None:
        """Called when SessionService switches active session. Loads history."""
        if not key:
            return
        if key == self._session_key and self._history_initialized:
            return
        if self._processing or self._active_streaming_row >= 0:
            self._pending_session_key = key
            return
        self._apply_session_key(key)

    def _apply_session_key(self, key: str) -> None:
        self._session_key = key
        self._history_fingerprint = None
        self._pending_history_refresh = False
        self._pending_system.clear()
        if self._session_manager is None:
            return
        self._request_history_load(key)

    @Slot()
    def _sync_active_history(self) -> None:
        if self._session_manager is None or not self._history_initialized:
            return
        if self._processing or self._active_streaming_row >= 0:
            return
        self._request_history_load(self._session_key)

    def _request_history_load(self, key: str) -> None:
        self._set_history_loading(True)
        self._history_request_seq += 1
        seq = self._history_request_seq
        self._history_latest_seq = seq
        fut = self._runner.submit(self._load_history(key, seq))
        fut.add_done_callback(self._on_history_done)

    async def _load_history(
        self, key: str, seq: int
    ) -> tuple[str, int, tuple[int, str], list[dict[str, Any]]]:
        """Load session message history from SessionManager (runs on asyncio thread)."""
        session = self._session_manager.get_or_create(key)
        raw_messages: Any
        try:
            raw_messages = session.get_display_history()
        except Exception:
            raw_messages = None
        if not isinstance(raw_messages, list):
            raw_messages = session.get_history() if hasattr(session, "get_history") else []
        fingerprint = self._history_signature(raw_messages)
        prepared_messages = ChatMessageModel.prepare_history(raw_messages)
        return key, seq, fingerprint, prepared_messages

    def _on_history_done(self, future: Any) -> None:
        """Runs on asyncio thread — only emits signal."""
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
        loaded_seq = 0
        loaded_messages = messages or []
        loaded_fingerprint: tuple[int, str] | None = None
        loaded_prepared = False
        if isinstance(messages, tuple) and len(messages) == 4:
            loaded_key, loaded_seq, loaded_fingerprint, loaded_messages = messages
            loaded_messages = loaded_messages or []
            loaded_prepared = True
        if isinstance(messages, tuple) and len(messages) == 3:
            loaded_key, loaded_seq, loaded_messages = messages
            loaded_messages = loaded_messages or []
        elif isinstance(messages, tuple) and len(messages) == 2:
            loaded_key, loaded_messages = messages
            loaded_messages = loaded_messages or []
        if loaded_seq and loaded_seq != self._history_latest_seq:
            return
        if loaded_key != self._session_key:
            return
        if self._processing or self._active_streaming_row >= 0:
            self._pending_history_refresh = True
            return
        fingerprint = loaded_fingerprint or self._history_signature(loaded_messages)
        if self._history_initialized and fingerprint == self._history_fingerprint:
            self._set_history_loading(False)
            return
        self._history_initialized = True
        self._history_fingerprint = fingerprint
        if loaded_prepared:
            self._model.load_prepared(loaded_messages)
        else:
            self._model.load_history(loaded_messages)
        self._set_history_loading(False)

    @staticmethod
    def _history_signature(messages: list[dict[str, Any]]) -> tuple[int, str]:
        if not messages:
            return (0, "")
        return (len(messages), repr(messages[-1]))

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
        try:
            config = load_config(config_path)
        except SystemExit:
            config = Config()

        # --- build shared gateway stack ---
        provider = make_provider(config)
        stack = build_gateway_stack(config, provider)

        # Store references for shutdown
        self._agent = stack.agent
        self._channels = stack.channels
        self._cron = stack.cron
        self._heartbeat = stack.heartbeat

        # Register callback for subagent completion notifications
        async def _on_system_response(msg: Any) -> None:
            if msg.content and msg.channel == "desktop":
                self._systemResponse.emit(msg.content)

        stack.agent.on_system_response = _on_system_response
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
                    on_desktop_greeting=lambda t: self._systemResponse.emit(t),
                )
            ),
        ]

        return stack.session_manager, stack.channels.enabled_channels

    def _on_init_done(self, future: Any) -> None:
        """Runs on asyncio thread — only emits signal."""
        exc = future.exception()
        if exc:
            self._initResult.emit(False, f"Gateway init failed: {exc}", None, [])
        else:
            sm, ch_list = future.result()
            self._initResult.emit(True, "", sm, ch_list)

    def _handle_init_result(
        self, ok: bool, error_msg: str, session_manager: Any, channels: list[str]
    ) -> None:
        """Runs on Qt main thread."""
        if not ok:
            self._set_error(error_msg)
            return
        self._set_state("running")
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
        self._model.append_system(" — ".join(parts))
        self._session_manager = session_manager
        self.gatewayReady.emit(session_manager, channels)
        self._drain_queue()

    # ------------------------------------------------------------------
    # Internal: message queue (serial)
    # ------------------------------------------------------------------

    def _enqueue(self, text: str) -> None:
        self._send_queue.put(text)
        if self._state == "running":
            self._drain_queue()

    def _drain_queue(self) -> None:
        with self._lock:
            if self._processing:
                return
            try:
                text = self._send_queue.get_nowait()
            except queue.Empty:
                return
            self._processing = True

        assistant_row = self._model.append_assistant("", status="typing")
        self._active_streaming_row = assistant_row
        self._active_has_content = False
        self._pending_split = False
        self.messageAppended.emit(assistant_row)

        fut = self._runner.submit(self._call_agent(text))
        fut.add_done_callback(lambda f: self._on_send_done(f, assistant_row))

    def _on_send_done(self, future: Any, row: int) -> None:
        """Runs on asyncio thread — only emits signal."""
        exc = future.exception()
        if exc:
            self._sendResult.emit(row, False, f"Error: {exc}")
        else:
            self._sendResult.emit(row, True, future.result() or "")

    def _handle_send_result(self, _row: int, ok: bool, content: str) -> None:
        """Runs on Qt main thread. Finalizes the active streaming bubble."""
        active = self._active_streaming_row if self._active_streaming_row >= 0 else _row
        if ok and self._pending_split and self._active_has_content and content:
            self._model.set_status(active, "done")
            active = self._model.append_assistant("", status="typing")
            self._active_streaming_row = active
            self._active_has_content = False
            self.messageAppended.emit(active)
        if not ok:
            self._model.update_content(active, content)
            self._model.set_status(active, "error")
        else:
            if content:
                self._model.update_content(active, content)
                self._active_has_content = True
            self._model.set_status(active, "done")
        self._active_streaming_row = -1
        self._active_has_content = False
        self._pending_split = False
        # Drain pending system responses before releasing lock
        pending: list[str] = []
        pending_session_key: str | None = None
        needs_history_refresh = False
        with self._lock:
            self._processing = False
            pending = self._pending_system[:]
            self._pending_system.clear()
            pending_session_key = self._pending_session_key
            self._pending_session_key = None
            needs_history_refresh = self._pending_history_refresh
            self._pending_history_refresh = False
        for msg in pending:
            self._show_system_response(msg)
        if pending_session_key and (
            pending_session_key != self._session_key or not self._history_initialized
        ):
            self._apply_session_key(pending_session_key)
        elif needs_history_refresh:
            self._request_history_load(self._session_key)

    async def _call_agent(self, text: str) -> str:
        if self._agent is None:
            raise RuntimeError("Agent not initialized")

        from bao.providers.retry import PROGRESS_RESET

        accumulated = [""]

        async def _on_progress(delta: str) -> None:
            if delta == PROGRESS_RESET:
                self._progressUpdate.emit(-2, "")
                accumulated[0] = ""
                return
            accumulated[0] += delta
            self._progressUpdate.emit(-1, accumulated[0])

        result = await self._agent.process_direct(
            text,
            session_key=self._session_key,
            channel="desktop",
            chat_id="local",
            on_progress=_on_progress,
        )
        return result

    def _handle_progress_update(self, row: int, content: str) -> None:
        """Runs on Qt main thread. Routes streaming content to active bubble."""
        if row == -2:
            self._pending_split = True
            return
        if row == -1 and self._pending_split:
            if self._active_has_content:
                cur = self._active_streaming_row
                if cur >= 0:
                    self._model.set_status(cur, "done")
                new_row = self._model.append_assistant("", status="typing")
                self._active_streaming_row = new_row
                self._active_has_content = False
                self.messageAppended.emit(new_row)
            self._pending_split = False
        target = self._active_streaming_row if row == -1 else row
        if target >= 0:
            self._model.update_content(target, content)
            self._active_has_content = bool(content)

    def _handle_system_response(self, content: str) -> None:
        """Runs on Qt main thread. Queue if streaming, else show immediately."""
        if not content:
            return
        with self._lock:
            if self._processing:
                self._pending_system.append(content)
                return
        self._show_system_response(content)

    def _show_system_response(self, content: str) -> None:
        """Display subagent completion as assistant message (no typewriter)."""
        row = self._model.append_assistant(content, status="done")
        self.messageAppended.emit(row)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _set_state(self, state: str) -> None:
        if self._state != state:
            self._state = state
            self.stateChanged.emit(state)

    def _set_history_loading(self, loading: bool) -> None:
        if self._history_loading != loading:
            self._history_loading = loading
            self.historyLoadingChanged.emit(loading)

    def _set_error(self, msg: str) -> None:
        self._last_error = msg
        self.errorChanged.emit(msg)
        self._model.append_system(f"⚠ {msg}", status="error")
        self._set_state("error")

    async def _shutdown_gateway(self) -> None:
        """Full shutdown mirroring CLI finally block."""
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
