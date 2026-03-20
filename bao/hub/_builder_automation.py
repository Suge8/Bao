from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from bao.agent.tools.cron import CronTool
from bao.hub._builder_targets import PrimaryTargetResolver
from bao.hub._control_types import HubSendRequest
from bao.hub._dispatcher import HubDispatcher
from bao.hub.control import HubControl

DEFAULT_HEARTBEAT_CHANNEL = "cli"
DEFAULT_HEARTBEAT_CHAT_ID = "direct"


@dataclass(frozen=True)
class CronRunContext:
    dispatcher: HubDispatcher
    bus: Any
    logger: Any
    profile_id: str
    delivery_sender: Any


@dataclass(frozen=True)
class HeartbeatContext:
    dispatcher: HubDispatcher
    bus: Any
    resolver: PrimaryTargetResolver
    profile_id: str
    delivery_sender: Any


def build_cron_prompt(job: Any) -> str:
    return (
        "[Scheduled Task] Timer finished.\n\n"
        f"Task '{job.name}' has been triggered.\n"
        f"Scheduled instruction: {job.payload.message}"
    )


async def run_cron_job(context: CronRunContext, job: Any) -> str | None:
    from bao.bus.events import OutboundMessage

    runtime = context.dispatcher.ensure_runtime(context.profile_id)
    cron_tool = runtime.agent.tools.get("cron")
    cron_token = None
    try:
        if isinstance(cron_tool, CronTool):
            cron_token = cron_tool.set_cron_context(True)
        response = await _hub_control(context.dispatcher).send(
            HubSendRequest(
                content=build_cron_prompt(job),
                session_key=f"cron:{job.id}",
                channel=job.payload.channel or "hub",
                chat_id=job.payload.to or "direct",
                profile_id=context.profile_id,
            )
        )
    except Exception as exc:
        context.logger.warning("⚠️ 定时任务失败 / cron failed: {} — {}", job.id, exc)
        return f"Error: {exc}"
    finally:
        if isinstance(cron_tool, CronTool) and cron_token is not None:
            cron_tool.reset_cron_context(cron_token)

    if job.payload.deliver and job.payload.to:
        await context.delivery_sender(
            OutboundMessage(
                channel=job.payload.channel or "hub",
                chat_id=job.payload.to,
                content=response or "",
            )
        )
    return response


def build_cron_handler(context: CronRunContext) -> Any:
    async def on_cron_job(job: Any) -> str | None:
        return await run_cron_job(context, job)

    return on_cron_job


def resolve_heartbeat_target(context: HeartbeatContext) -> tuple[str, str]:
    target = context.resolver.pick()
    if target is None:
        return DEFAULT_HEARTBEAT_CHANNEL, DEFAULT_HEARTBEAT_CHAT_ID
    return target


async def silent_progress(*_args: Any, **_kwargs: Any) -> None:
    return None


async def execute_heartbeat(context: HeartbeatContext, tasks: str) -> str:
    channel, chat_id = resolve_heartbeat_target(context)
    return await _hub_control(context.dispatcher).send(
        HubSendRequest(
            content=tasks,
            session_key="heartbeat",
            channel=channel,
            chat_id=chat_id,
            profile_id=context.profile_id,
            on_progress=silent_progress,
        )
    )


async def notify_heartbeat(context: HeartbeatContext, response: str) -> None:
    from bao.bus.events import OutboundMessage

    target = context.resolver.pick()
    if target is None:
        return
    channel_name, chat_id = target
    await context.delivery_sender(
        OutboundMessage(channel=channel_name, chat_id=chat_id, content=response)
    )


def _hub_control(dispatcher: HubDispatcher) -> HubControl:
    return HubControl(dispatcher)


def build_heartbeat_service(
    *,
    config: Any,
    provider: Any,
    logger: Any,
    bus: Any,
    prompt_root: Any,
    dispatcher: HubDispatcher,
    profile_id: str,
    delivery_sender: Any,
) -> Any:
    from bao.heartbeat._service_models import HeartbeatServiceOptions
    from bao.heartbeat.service import HeartbeatService

    heartbeat_context = HeartbeatContext(
        dispatcher=dispatcher,
        bus=bus,
        resolver=PrimaryTargetResolver(config, logger),
        profile_id=profile_id,
        delivery_sender=delivery_sender,
    )
    heartbeat_config = config.hub.heartbeat

    async def on_execute(tasks: str) -> str:
        return await execute_heartbeat(heartbeat_context, tasks)

    async def on_notify(response: str) -> None:
        await notify_heartbeat(heartbeat_context, response)

    return HeartbeatService(
        HeartbeatServiceOptions(
            workspace=prompt_root,
            provider=provider,
            model=config.agents.defaults.model,
            on_execute=on_execute,
            on_notify=on_notify,
            interval_s=heartbeat_config.interval_s,
            enabled=heartbeat_config.enabled,
            service_tier=config.agents.defaults.service_tier,
        )
    )
