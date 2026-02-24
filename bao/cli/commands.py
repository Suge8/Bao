from __future__ import annotations

import asyncio
import sys

import typer
from rich.console import Console

from bao import __logo__, __version__
from bao.config.schema import Config

app = typer.Typer(name="bao", help=f"{__logo__} bao - Gateway", invoke_without_command=True)
console = Console()


def version_callback(value: bool) -> None:
    if value:
        console.print(f"{__logo__} bao v{__version__}")
        raise typer.Exit()


def _make_provider(config: Config):
    from bao.providers import make_provider

    try:
        return make_provider(config)
    except ValueError as e:
        from bao.config.loader import get_config_path

        console.print(f"\n[yellow]⚠ {e}[/yellow]")
        console.print("  请在配置文件中填入 API Key / Please add your API key in:")
        console.print(f"     {get_config_path()}\n")
        raise typer.Exit(1)


def _setup_logging(verbose: bool) -> None:
    import logging

    from loguru import logger

    logger.remove()
    logging.basicConfig(level=logging.WARNING)
    for name in ("httpcore", "httpx", "openai"):
        logging.getLogger(name).setLevel(logging.WARNING)

    if verbose:
        logger.add(sys.stderr, level="DEBUG")
    else:
        logger.add(sys.stderr, level="INFO", format="{time:HH:mm:ss} | {message}")


async def _send_startup_greeting(agent, bus, config) -> None:
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
    from bao.config.loader import detect_onboarding_stage, infer_language, LANG_PICKER, PERSONA_GREETING
    stage = detect_onboarding_stage(config.workspace_path)
    if stage == "lang_select":
        for ch, cid in targets:
            await bus.publish_outbound(OutboundMessage(channel=ch, chat_id=cid, content=LANG_PICKER))
        return
    if stage == "persona_setup":
        greeting = PERSONA_GREETING[infer_language(config.workspace_path)]
        for ch, cid in targets:
            await bus.publish_outbound(OutboundMessage(channel=ch, chat_id=cid, content=greeting))
        return

    prompt = (
        "You just came online. Greet the user in character based on your PERSONA.md personality. "
        "Mention the current time naturally. Don't self-introduce. "
        "Keep it short, like an old friend saying hi."
    )
    try:
        greeting = await agent.process_direct(prompt, session_key="system:greeting")
    except Exception as e:
        logger.warning("Startup greeting failed: {}", e)
        return

    if greeting:
        for ch, cid in targets:
            await bus.publish_outbound(OutboundMessage(channel=ch, chat_id=cid, content=greeting))


def run_gateway(port: int, verbose: bool) -> None:
    from bao.agent.loop import AgentLoop
    from bao.bus.events import OutboundMessage
    from bao.bus.queue import MessageBus
    from bao.channels.manager import ChannelManager
    from bao.config.loader import get_data_dir, load_config
    from bao.cron.service import CronService
    from bao.cron.types import CronJob
    from bao.heartbeat.service import HeartbeatService
    from bao.session.manager import SessionManager

    _setup_logging(verbose)

    if not isinstance(port, int):
        port = 18790
    console.print(f"\n{__logo__} 启动 bao 网关 / Starting bao gateway on port {port}...")

    config = load_config()
    bus = MessageBus()
    provider = _make_provider(config)
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

    async def on_cron_job(job: CronJob) -> str | None:
        response = await agent.process_direct(
            job.payload.message,
            session_key=f"cron:{job.id}",
            channel=job.payload.channel or "gateway",
            chat_id=job.payload.to or "direct",
        )
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

    async def on_heartbeat(prompt: str) -> str:
        return await agent.process_direct(prompt, session_key="heartbeat")

    heartbeat = HeartbeatService(
        workspace=config.workspace_path,
        on_heartbeat=on_heartbeat,
        interval_s=30 * 60,
        enabled=True,
    )

    channels = ChannelManager(config, bus)
    if channels.enabled_channels:
        console.print(f"  📡 已启用通道 / Channels: {', '.join(channels.enabled_channels)}")
    else:
        console.print("  [yellow]📡 未启用任何通道 / No channels enabled[/yellow]")

    cron_status = cron.status()
    if cron_status["jobs"] > 0:
        console.print(f"  ⏰ 定时任务 / Cron: {cron_status['jobs']} jobs")
    console.print("  💓 心跳检查 / Heartbeat: every 30m")

    async def run() -> None:
        try:
            await cron.start()
            await heartbeat.start()
            await asyncio.gather(
                agent.run(),
                channels.start_all(),
                _send_startup_greeting(agent, bus, config),
            )
        except KeyboardInterrupt:
            console.print("\n👋 正在关闭 / Shutting down...")
        finally:
            await agent.close_mcp()
            heartbeat.stop()
            cron.stop()
            agent.stop()
            await channels.stop_all()

    asyncio.run(run())


@app.callback()
def main(
    port: int = typer.Option(18790, "--port", "-p", help="Gateway port"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
    version: bool = typer.Option(False, "--version", callback=version_callback, is_eager=True),
) -> None:
    _ = version
    run_gateway(port=port, verbose=verbose)


if __name__ == "__main__":
    app()
