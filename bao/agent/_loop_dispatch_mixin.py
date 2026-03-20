from __future__ import annotations

import asyncio
import uuid
from typing import Any, Awaitable, cast

from loguru import logger

from bao.agent._loop_user_message_models import ProcessMessageOptions
from bao.bus.events import ControlEvent, InboundMessage, OutboundMessage
from bao.hub import HubStopRequest, local_hub_control
from bao.runtime_diagnostics_models import RuntimeEventRequest


class LoopDispatchMixin:
    @staticmethod
    def _dispatch_session_key(msg: InboundMessage) -> str:
        override = msg.metadata.get("session_key")
        if isinstance(override, str) and override:
            return override
        if msg.channel == "system":
            if ":" in msg.chat_id:
                origin_channel, origin_chat_id = msg.chat_id.split(":", 1)
                return f"{origin_channel}:{origin_chat_id}"
            return f"hub:{msg.chat_id}"
        return msg.session_key

    @staticmethod
    def _dispatch_control_session_key(event: ControlEvent) -> str:
        session_key = event.session_key.strip()
        if session_key:
            return session_key
        channel = event.origin_channel.strip() or "hub"
        chat_id = event.origin_chat_id.strip() or "direct"
        return f"{channel}:{chat_id}"

    async def _consume_next_bus_item(self) -> tuple[str, InboundMessage | ControlEvent]:
        inbound_task = asyncio.create_task(self.bus.consume_inbound())
        control_task = asyncio.create_task(self.bus.consume_control())
        try:
            done, pending = await asyncio.wait({inbound_task, control_task}, return_when=asyncio.FIRST_COMPLETED)
        except asyncio.CancelledError:
            for task in (inbound_task, control_task):
                task.cancel()
            await asyncio.gather(inbound_task, control_task, return_exceptions=True)
            raise
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        return ("inbound", inbound_task.result()) if inbound_task in done else ("control", control_task.result())

    def _schedule_session_task(self, dispatch_key: str, coro: Awaitable[None]) -> None:
        self._session_runs.schedule(dispatch_key, coro)

    async def run(self) -> None:
        self._running = True
        self._run_task = asyncio.current_task()
        await self._connect_mcp()
        logger.debug("Agent loop started")
        try:
            while self._running:
                try:
                    item_kind, item = await self._consume_next_bus_item()
                except asyncio.CancelledError:
                    if self._running:
                        raise
                    break
                if item_kind == "control":
                    control_event = cast(ControlEvent, item)
                    session_key = self._dispatch_control_session_key(control_event)
                    self._schedule_session_task(session_key, self._dispatch_control(control_event, dispatch_key=session_key))
                    continue
                msg = cast(InboundMessage, item)
                if (msg.content or "").strip().lower() == "/stop":
                    await self._handle_stop_request(msg)
                    continue
                session_key = self._dispatch_session_key(msg)
                await self._schedule_message_dispatch(msg, session_key)
        finally:
            if self._run_task is asyncio.current_task():
                self._run_task = None

    async def _handle_stop_request(self, msg: InboundMessage) -> None:
        await self._handle_stop(msg)

    async def _schedule_message_dispatch(self, msg: InboundMessage, session_key: str) -> None:
        resolve_mode = getattr(cast(Any, self.provider), "_resolve_effective_mode", None)
        interrupt_request = self._session_runs.request_interrupt(
            session_key,
            cancel_running=bool(callable(resolve_mode) and resolve_mode() == "responses"),
        )
        if interrupt_request.has_busy_work:
            await self._pre_save_interrupted_user_message(msg, session_key)
            logger.debug("Soft interrupt requested for busy session {}", session_key)
        task_gen = self._session_runs.generation(session_key)
        self._schedule_session_task(session_key, self._dispatch(msg, task_generation=task_gen, dispatch_key=session_key))

    async def _pre_save_interrupted_user_message(self, msg: InboundMessage, session_key: str) -> None:
        cmd = (msg.content or "").strip().lower()
        if msg.channel == "system" or cmd.startswith("/"):
            return
        natural_key = msg.session_key
        active_override = self.sessions.get_active_session_key(natural_key)
        key = active_override or natural_key
        session = self.sessions.get_or_create(key)
        pre_saved_token = msg.metadata.get("_pre_saved_token")
        if not isinstance(pre_saved_token, str) or not pre_saved_token:
            pre_saved_token = uuid.uuid4().hex
            msg.metadata["_pre_saved_token"] = pre_saved_token
        session.add_message("user", msg.content, _pre_saved=True, _pre_saved_token=pre_saved_token)
        self.sessions.save(session)
        msg.metadata["_pre_saved"] = True

    async def _handle_stop(self, msg: InboundMessage) -> None:
        natural_key = self._dispatch_session_key(msg)
        total = await local_hub_control(
            session_manager=self.sessions,
            agent=self,
            session_runs=self._session_runs,
        ).stop(HubStopRequest(session_key=natural_key))
        content = f"\u23f9 Stopped {total} task(s)." if total else "No active task to stop."
        out_meta = dict(msg.metadata or {})
        reply_to = out_meta.get("reply_to") if isinstance(out_meta.get("reply_to"), str) else None
        await self.bus.publish_outbound(OutboundMessage(channel=msg.channel, chat_id=msg.chat_id, content=content, reply_to=reply_to, metadata=out_meta))

    async def _dispatch(self, msg: InboundMessage, *, task_generation: int, dispatch_key: str) -> None:
        async with self._session_runs.run_scope(dispatch_key):
            try:
                response = await self._process_message(
                    msg,
                    ProcessMessageOptions(
                        expected_generation=task_generation,
                        expected_generation_key=dispatch_key,
                    ),
                )
                if not response:
                    return
                if self._session_runs.is_stale(dispatch_key, task_generation):
                    logger.debug("Dropping stale response for session {} after /stop", dispatch_key)
                    return
                if msg.channel == "system" and self.on_system_response:
                    try:
                        await self.on_system_response(response)
                    except Exception as cb_err:
                        logger.debug("on_system_response callback failed: {}", cb_err)
                await self.bus.publish_outbound(response)
            except asyncio.CancelledError:
                logger.debug("Task cancelled for session {}", dispatch_key)
                raise
            except Exception as exc:
                logger.error("❌ 消息处理失败 / message error: {}", exc)
                self._record_runtime_diagnostic(
                    RuntimeEventRequest(
                        source="agent_loop",
                        stage="dispatch",
                        message=str(exc),
                        code="message_error",
                        retryable=False,
                        session_key=dispatch_key,
                    )
                )
                if self._session_runs.is_stale(dispatch_key, task_generation):
                    logger.debug("Suppressing stale error response for session {}", dispatch_key)
                    return
                await self.bus.publish_outbound(OutboundMessage(channel=msg.channel, chat_id=msg.chat_id, content=f"Sorry, I encountered an error: {str(exc)}"))

    async def _dispatch_control(self, event: ControlEvent, *, dispatch_key: str) -> None:
        async with self._session_runs.run_scope(dispatch_key):
            try:
                response = await self._process_control_event(event)
                if not response:
                    return
                if self.on_system_response:
                    try:
                        await self.on_system_response(response)
                    except Exception as cb_err:
                        logger.debug("on_system_response callback failed: {}", cb_err)
                await self.bus.publish_outbound(response)
            except asyncio.CancelledError:
                logger.debug("Control event cancelled for session {}", dispatch_key)
                raise
            except Exception as exc:
                logger.error("❌ 控制事件处理失败 / control event error: {}", exc)
                self._record_runtime_diagnostic(
                    RuntimeEventRequest(
                        source="agent_loop",
                        stage="control_dispatch",
                        message=str(exc),
                        code="control_event_error",
                        retryable=False,
                        session_key=dispatch_key,
                        details={"kind": event.kind, "source": event.source},
                    )
                )

    async def close_mcp(self) -> None:
        if self._mcp_stack:
            try:
                await self._mcp_stack.aclose()
            except (RuntimeError, BaseExceptionGroup):
                pass
            self._mcp_stack = None
        self._mcp_connect_succeeded = False
        self._mcp_connected = False

    def stop(self) -> None:
        self._running = False
        run_task = getattr(self, "_run_task", None)
        if run_task and not run_task.done():
            run_task.cancel()
        logger.info("👋 停止代理 / agent stopping: main loop")

    def close(self) -> None:
        self._running = False
        self.context.close()
        self.sessions.close()
