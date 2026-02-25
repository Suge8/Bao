"""ChatService — embedded bao gateway lifecycle + serial message queue.

State machine: idle -> starting -> running -> stopped / error

Full gateway: AgentLoop + ChannelManager + CronService + HeartbeatService,
functionally equivalent to the CLI ``bao`` command.
All bao core calls happen on the asyncio thread via AsyncioRunner.
Internal signals marshal results back to the Qt main thread.
"""

from __future__ import annotations

import asyncio
import queue
import threading
from typing import Any

from PySide6.QtCore import QObject, QTimer, Signal, Property, Slot

from app.backend.asyncio_runner import AsyncioRunner
from app.backend.chat import ChatMessageModel


class ChatService(QObject):
    stateChanged = Signal(str)
    errorChanged = Signal(str)
    messageAppended = Signal(int)
    contentUpdated = Signal(int, str)
    statusUpdated = Signal(int, str)
    gatewayReady = Signal(object, list)  # session_manager, enabled_channels

    # Internal signals: asyncio thread → Qt main thread marshaling
    _initResult = Signal(bool, str, object, list)  # ok, err, session_mgr, channels
    _sendResult = Signal(int, bool, str)  # row, ok, content_or_error
    _historyResult = Signal(bool, str, object)  # ok, error, messages_list

    def __init__(self, model: ChatMessageModel, parent: Any = None) -> None:
        super().__init__(parent)
        self._model = model
        self._runner = AsyncioRunner()
        self._state = "idle"
        self._last_error = ""
        self._agent: Any = None
        self._channels: Any = None
        self._cron: Any = None
        self._heartbeat: Any = None
        self._background_tasks: list[asyncio.Task] = []
        self._session_key = "desktop:local"
        self._send_queue: queue.Queue[str] = queue.Queue()
        self._processing = False
        self._lock = threading.Lock()
        self._cron_status: dict = {}
        self._session_manager: Any = None

        self._initResult.connect(self._handle_init_result)
        self._sendResult.connect(self._handle_send_result)
        self._historyResult.connect(self._handle_history_result)

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

    # ------------------------------------------------------------------
    # Public slots
    # ------------------------------------------------------------------

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
        self._runner.shutdown(grace_s=5.0)

    @Slot()
    def restart(self) -> None:
        self.stop()
        QTimer.singleShot(300, self.start)

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
        if not key or key == self._session_key:
            return
        self._session_key = key
        if self._session_manager is None:
            return
        fut = self._runner.submit(self._load_history(key))
        fut.add_done_callback(self._on_history_done)

    async def _load_history(self, key: str) -> list[dict]:
        """Load session message history from SessionManager (runs on asyncio thread)."""
        session = self._session_manager.get_or_create(key)
        return session.get_history()

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
            return
        self._model.load_history(messages or [])
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

        # --- start background services on the asyncio loop ---
        loop = asyncio.get_running_loop()
        await stack.cron.start()
        await stack.heartbeat.start()
        self._cron_status = stack.cron.status()
        self._background_tasks = [
            loop.create_task(stack.agent.run()),
            loop.create_task(stack.channels.start_all()),
            loop.create_task(send_startup_greeting(stack.agent, stack.bus, stack.config)),
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
        self, ok: bool, error_msg: str, session_manager: Any, channels: list
    ) -> None:
        """Runs on Qt main thread."""
        if not ok:
            self._set_error(error_msg)
            return
        self._set_state("running")
        # Build status message (mirrors CLI output)
        parts = ["✓ Gateway started"]
        if channels:
            parts.append(f"channels: {', '.join(channels)}")
        cron_jobs = self._cron_status.get("jobs", 0)
        if cron_jobs > 0:
            parts.append(f"cron: {cron_jobs} jobs")
        parts.append("heartbeat: every 30m")
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
        self.messageAppended.emit(assistant_row)

        fut = self._runner.submit(self._call_agent(text, assistant_row))
        fut.add_done_callback(lambda f: self._on_send_done(f, assistant_row))

    def _on_send_done(self, future: Any, row: int) -> None:
        """Runs on asyncio thread — only emits signal."""
        exc = future.exception()
        if exc:
            self._sendResult.emit(row, False, f"Error: {exc}")
        else:
            self._sendResult.emit(row, True, future.result() or "")

    def _handle_send_result(self, row: int, ok: bool, content: str) -> None:
        """Runs on Qt main thread."""
        if not ok:
            self._model.update_content(row, content)
            self._model.set_status(row, "error")
        else:
            self._start_typewriter(row, content)

        with self._lock:
            self._processing = False
        self._drain_queue()

    async def _call_agent(self, text: str, _row: int) -> str:
        if self._agent is None:
            raise RuntimeError("Agent not initialized")
        return await self._agent.process_direct(
            text,
            session_key=self._session_key,
            channel="desktop",
            chat_id="local",
        )

    # ------------------------------------------------------------------
    # Typewriter effect (runs on Qt main thread)
    # ------------------------------------------------------------------

    def _start_typewriter(self, row: int, full_text: str) -> None:
        if not full_text:
            self._model.set_status(row, "done")
            return

        chunk_size = 4
        interval_ms = 20
        pos = [0]

        def tick() -> None:
            end = min(pos[0] + chunk_size, len(full_text))
            self._model.update_content(row, full_text[:end])
            pos[0] = end
            if pos[0] >= len(full_text):
                self._model.set_status(row, "done")
            else:
                QTimer.singleShot(interval_ms, tick)

        QTimer.singleShot(interval_ms, tick)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _set_state(self, state: str) -> None:
        if self._state != state:
            self._state = state
            self.stateChanged.emit(state)

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

