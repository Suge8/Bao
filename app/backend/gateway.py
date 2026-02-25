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
        from bao.agent.loop import AgentLoop
        from bao.bus.queue import MessageBus
        from bao.channels.manager import ChannelManager
        from bao.config.loader import (
            get_config_path,
            get_data_dir,
            load_config,
            save_config,
            _ensure_workspace,
        )
        from bao.config.schema import Config
        from bao.cron.service import CronService
        from bao.heartbeat.service import HeartbeatService
        from bao.providers import make_provider
        from bao.session.manager import SessionManager

        # --- config ---
        config_path = get_config_path()
        if not config_path.exists():
            config = Config()
            save_config(config)
            _ensure_workspace(config)
            config_path = get_config_path()

        try:
            config = load_config(config_path)
        except SystemExit:
            config = Config()

        # --- core services (same as CLI) ---
        bus = MessageBus()
        provider = make_provider(config)
        session_manager = SessionManager(config.workspace_path)
        cron = CronService(get_data_dir() / "cron" / "jobs.json")

        agent = AgentLoop(
            bus=bus,
            provider=provider,
            workspace=config.workspace_path,
            model=config.agents.defaults.model,
            temperature=config.agents.defaults.temperature,
            max_tokens=config.agents.defaults.max_tokens,
            max_iterations=config.agents.defaults.max_tool_iterations,
            memory_window=config.agents.defaults.memory_window,
            search_config=config.tools.web.search,
            exec_config=config.tools.exec,
            cron_service=cron,
            embedding_config=config.tools.embedding,
            restrict_to_workspace=config.tools.restrict_to_workspace,
            session_manager=session_manager,
            mcp_servers=config.tools.mcp_servers,
            available_models=config.agents.defaults.models,
            config=config,
        )

        # --- cron callback ---
        from bao.bus.events import OutboundMessage

        async def on_cron_job(job) -> str | None:
            from loguru import logger
            try:
                response = await agent.process_direct(
                    job.payload.message,
                    session_key=f"cron:{job.id}",
                    channel=job.payload.channel or "gateway",
                    chat_id=job.payload.to or "direct",
                )
            except Exception as e:
                logger.warning("Cron job {} failed: {}", job.id, e)
                return f"Error: {e}"
            if job.payload.deliver and job.payload.to:
                await bus.publish_outbound(
                    OutboundMessage(
                        channel=job.payload.channel or "gateway",
                        chat_id=job.payload.to,
                        content=response or "",
                    )
                )
            return response

        cron.on_job = on_cron_job

        # --- heartbeat ---
        async def on_heartbeat(prompt: str) -> str:
            return await agent.process_direct(prompt, session_key="heartbeat")

        heartbeat = HeartbeatService(
            workspace=config.workspace_path,
            on_heartbeat=on_heartbeat,
            interval_s=30 * 60,
            enabled=True,
        )

        # --- channels ---
        channels = ChannelManager(config, bus)

        # Store references for shutdown
        self._agent = agent
        self._channels = channels
        self._cron = cron
        self._heartbeat = heartbeat

        # --- start background services on the asyncio loop ---
        loop = asyncio.get_running_loop()
        await cron.start()
        await heartbeat.start()
        self._cron_status = cron.status()
        self._background_tasks = [
            loop.create_task(agent.run()),
            loop.create_task(channels.start_all()),
            loop.create_task(self._send_startup_greeting(agent, bus, config)),
        ]

        return session_manager, channels.enabled_channels

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

    @staticmethod
    async def _send_startup_greeting(agent: Any, bus: Any, config: Any) -> None:
        """Send startup greeting to all enabled channels (mirrors CLI behavior)."""
        from loguru import logger
        from bao.bus.events import OutboundMessage

        await asyncio.sleep(5)
        channel_cfgs = [
            ("telegram", config.channels.telegram),
            ("imessage", config.channels.imessage),
            ("whatsapp", config.channels.whatsapp),
            ("dingtalk", config.channels.dingtalk),
        ]
        targets = [
            (name, uid.split("|")[0])
            for name, cfg in channel_cfgs
            if cfg.enabled and cfg.allow_from
            for uid in cfg.allow_from
        ]
        if not targets:
            return

        from bao.config.loader import (
            detect_onboarding_stage,
            infer_language,
            LANG_PICKER,
            PERSONA_GREETING,
        )

        stage = detect_onboarding_stage(config.workspace_path)
        if stage == "lang_select":
            for ch, cid in targets:
                await bus.publish_outbound(
                    OutboundMessage(channel=ch, chat_id=cid, content=LANG_PICKER)
                )
            return
        if stage == "persona_setup":
            greeting = PERSONA_GREETING[infer_language(config.workspace_path)]
            for ch, cid in targets:
                await bus.publish_outbound(
                    OutboundMessage(channel=ch, chat_id=cid, content=greeting)
                )
            return

        prompt = (
            "You just came online. Greet the user in character based on your "
            "PERSONA.md personality. Mention the current time naturally. "
            "Don't self-introduce. Keep it short, like an old friend saying hi."
        )
        try:
            greeting = await agent.process_direct(prompt, session_key="system:greeting")
        except Exception as e:
            logger.warning("Startup greeting failed: {}", e)
            return

        if greeting:
            for ch, cid in targets:
                await bus.publish_outbound(
                    OutboundMessage(channel=ch, chat_id=cid, content=greeting)
                )
