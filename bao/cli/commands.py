"""CLI commands for bao."""

import asyncio
import os
import signal
from pathlib import Path
import select
import sys

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.table import Table
from rich.text import Text

from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.history import FileHistory
from prompt_toolkit.patch_stdout import patch_stdout

from bao import __version__, __logo__
from bao.config.schema import Config

app = typer.Typer(
    name="bao",
    help=f"{__logo__} bao - Personal AI Assistant",
    invoke_without_command=True,
)

console = Console()
EXIT_COMMANDS = {"exit", "quit", "/exit", "/quit", ":q"}

# ---------------------------------------------------------------------------
# CLI input: prompt_toolkit for editing, paste, history, and display
# ---------------------------------------------------------------------------

_PROMPT_SESSION: PromptSession | None = None
_SAVED_TERM_ATTRS = None  # original termios settings, restored on exit


def _flush_pending_tty_input() -> None:
    """Drop unread keypresses typed while the model was generating output."""
    try:
        fd = sys.stdin.fileno()
        if not os.isatty(fd):
            return
    except Exception:
        return

    try:
        import termios

        termios.tcflush(fd, termios.TCIFLUSH)
        return
    except Exception:
        pass

    try:
        while True:
            ready, _, _ = select.select([fd], [], [], 0)
            if not ready:
                break
            if not os.read(fd, 4096):
                break
    except Exception:
        return


def _restore_terminal() -> None:
    """Restore terminal to its original state (echo, line buffering, etc.)."""
    if _SAVED_TERM_ATTRS is None:
        return
    try:
        import termios

        termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, _SAVED_TERM_ATTRS)
    except Exception:
        pass


def _init_prompt_session() -> None:
    """Create the prompt_toolkit session with persistent file history."""
    global _PROMPT_SESSION, _SAVED_TERM_ATTRS

    # Save terminal state so we can restore it on exit
    try:
        import termios

        _SAVED_TERM_ATTRS = termios.tcgetattr(sys.stdin.fileno())
    except Exception:
        pass

    history_file = Path.home() / ".bao" / "history" / "cli_history"
    history_file.parent.mkdir(parents=True, exist_ok=True)

    _PROMPT_SESSION = PromptSession(
        history=FileHistory(str(history_file)),
        enable_open_in_editor=False,
        multiline=False,  # Enter submits (single line mode)
    )


def _print_agent_response(response: str, render_markdown: bool) -> None:
    """Render assistant response with consistent terminal styling."""
    content = response or ""
    body = Markdown(content) if render_markdown else Text(content)
    console.print()
    console.print(f"[cyan]{__logo__} bao[/cyan]")
    console.print(body)
    console.print()


def _is_exit_command(command: str) -> bool:
    """Return True when input should end interactive chat."""
    return command.lower() in EXIT_COMMANDS


async def _read_interactive_input_async() -> str:
    """Read user input using prompt_toolkit (handles paste, history, display).

    prompt_toolkit natively handles:
    - Multiline paste (bracketed paste mode)
    - History navigation (up/down arrows)
    - Clean display (no ghost characters or artifacts)
    """
    if _PROMPT_SESSION is None:
        raise RuntimeError("Call _init_prompt_session() first")
    try:
        with patch_stdout():
            return await _PROMPT_SESSION.prompt_async(
                HTML("<b fg='ansiblue'>You:</b> "),
            )
    except EOFError as exc:
        raise KeyboardInterrupt from exc


def version_callback(value: bool):
    if value:
        console.print(f"{__logo__} bao v{__version__}")
        raise typer.Exit()


@app.callback()
def main(
    ctx: typer.Context,
    version: bool = typer.Option(None, "--version", "-v", callback=version_callback, is_eager=True),
):
    """bao - Personal AI Assistant."""
    if ctx.invoked_subcommand is None:
        gateway()


def _make_provider(config: Config):
    """Create the appropriate LLM provider from config."""
    from bao.providers import make_provider

    try:
        return make_provider(config)
    except ValueError as e:
        console.print(f"[red]Error: {e}[/red]")
        console.print("Set one in ~/.bao/config.jsonc under providers section")
        raise typer.Exit(1)


# ============================================================================
# Gateway / Server
# ============================================================================


@app.command()
def gateway(
    port: int = typer.Option(18790, "--port", "-p", help="Gateway port"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
):
    """Start the bao gateway."""
    from bao.config.loader import load_config, get_data_dir
    from bao.bus.queue import MessageBus
    from bao.agent.loop import AgentLoop
    from bao.channels.manager import ChannelManager
    from bao.session.manager import SessionManager
    from bao.cron.service import CronService
    from bao.cron.types import CronJob
    from bao.heartbeat.service import HeartbeatService

    from loguru import logger

    logger.remove()
    if verbose:
        import logging

        logging.basicConfig(level=logging.DEBUG)
        logger.add(sys.stderr, level="DEBUG")
    else:
        logger.add(sys.stderr, level="INFO", format="{time:HH:mm:ss} | {message}")

    console.print(f"{__logo__} Starting bao gateway on port {port}...")

    config = load_config()
    bus = MessageBus()
    provider = _make_provider(config)
    session_manager = SessionManager(config.workspace_path)

    # Create cron service first (callback set after agent creation)
    cron_store_path = get_data_dir() / "cron" / "jobs.json"
    cron = CronService(cron_store_path)

    # Create agent with cron service
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

    # Set cron callback (needs agent)
    async def on_cron_job(job: CronJob) -> str | None:
        """Execute a cron job through the agent."""
        response = await agent.process_direct(
            job.payload.message,
            session_key=f"cron:{job.id}",
            channel=job.payload.channel or "cli",
            chat_id=job.payload.to or "direct",
        )
        if job.payload.deliver and job.payload.to:
            from bao.bus.events import OutboundMessage

            await bus.publish_outbound(
                OutboundMessage(
                    channel=job.payload.channel or "cli",
                    chat_id=job.payload.to,
                    content=response or "",
                )
            )
        return response

    cron.on_job = on_cron_job

    # Create heartbeat service
    async def on_heartbeat(prompt: str) -> str:
        """Execute heartbeat through the agent."""
        return await agent.process_direct(prompt, session_key="heartbeat")

    heartbeat = HeartbeatService(
        workspace=config.workspace_path,
        on_heartbeat=on_heartbeat,
        interval_s=30 * 60,  # 30 minutes
        enabled=True,
    )

    # Create channel manager
    channels = ChannelManager(config, bus)

    if channels.enabled_channels:
        console.print(f"[green]✓[/green] Channels enabled: {', '.join(channels.enabled_channels)}")
    else:
        console.print("[yellow]Warning: No channels enabled[/yellow]")

    cron_status = cron.status()
    if cron_status["jobs"] > 0:
        console.print(f"[green]✓[/green] Cron: {cron_status['jobs']} scheduled jobs")

    console.print(f"[green]✓[/green] Heartbeat: every 30m")

    async def send_startup_greeting():
        await asyncio.sleep(5)

        from loguru import logger
        from bao.bus.events import OutboundMessage

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

        user_md = config.workspace_path / "PERSONA.md"
        is_new_user = not user_md.exists() or "(your name)" in user_md.read_text(encoding="utf-8")

        if is_new_user:
            prompt = (
                "You just came online for the first time. "
                "The user hasn't introduced themselves yet. Guide them through initial setup: "
                "ask their name, what they'd like to call you, and their preferred communication style. "
                "Tell them you'll remember these. Keep it brief and natural, not like a form. "
                "Respond in the user's language based on your PERSONA.md config."
            )
        else:
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
                await bus.publish_outbound(
                    OutboundMessage(channel=ch, chat_id=cid, content=greeting)
                )

    async def run():
        try:
            await cron.start()
            await heartbeat.start()
            await asyncio.gather(
                agent.run(),
                channels.start_all(),
                send_startup_greeting(),
            )
        except KeyboardInterrupt:
            console.print("\nShutting down...")
        finally:
            await agent.close_mcp()
            heartbeat.stop()
            cron.stop()
            agent.stop()
            await channels.stop_all()

    asyncio.run(run())


# ============================================================================
# Agent Commands
# ============================================================================


@app.command()
def agent(
    message: str = typer.Option(None, "--message", "-m", help="Message to send to the agent"),
    session_id: str = typer.Option("cli:direct", "--session", "-s", help="Session ID"),
    markdown: bool = typer.Option(
        True, "--markdown/--no-markdown", help="Render assistant output as Markdown"
    ),
    logs: bool = typer.Option(False, "--logs/--no-logs", help="Show bao runtime logs during chat"),
):
    """Interact with the agent directly."""
    from bao.config.loader import load_config, get_data_dir
    from bao.bus.queue import MessageBus
    from bao.agent.loop import AgentLoop
    from bao.cron.service import CronService
    from loguru import logger

    config = load_config()

    bus = MessageBus()
    provider = _make_provider(config)

    # Create cron service for tool usage (no callback needed for CLI unless running)
    cron_store_path = get_data_dir() / "cron" / "jobs.json"
    cron = CronService(cron_store_path)

    if logs:
        logger.enable("bao")
    else:
        logger.disable("bao")

    agent_loop = AgentLoop(
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
        mcp_servers=config.tools.mcp_servers,
        available_models=config.agents.defaults.models,
        config=config,
    )

    # Show spinner when logs are off (no output to miss); skip when logs are on
    def _thinking_ctx():
        if logs:
            from contextlib import nullcontext

            return nullcontext()
        # Animated spinner is safe to use with prompt_toolkit input handling
        return console.status("[dim]bao is thinking...[/dim]", spinner="dots")

    async def _cli_progress(content: str) -> None:
        console.print(f"  [dim]↳ {content}[/dim]")

    if message:
        # Single message mode
        async def run_once():
            with _thinking_ctx():
                response = await agent_loop.process_direct(
                    message, session_id, on_progress=_cli_progress
                )
            _print_agent_response(response, render_markdown=markdown)
            await agent_loop.close_mcp()

        asyncio.run(run_once())
    else:
        # Interactive mode
        _init_prompt_session()
        console.print(
            f"{__logo__} Interactive mode (type [bold]exit[/bold] or [bold]Ctrl+C[/bold] to quit)\n"
        )

        def _exit_on_sigint(signum, frame):
            _restore_terminal()
            console.print("\nGoodbye!")
            os._exit(0)

        signal.signal(signal.SIGINT, _exit_on_sigint)

        async def run_interactive():
            try:
                while True:
                    try:
                        _flush_pending_tty_input()
                        user_input = await _read_interactive_input_async()
                        command = user_input.strip()
                        if not command:
                            continue

                        if _is_exit_command(command):
                            _restore_terminal()
                            console.print("\nGoodbye!")
                            break

                        with _thinking_ctx():
                            response = await agent_loop.process_direct(
                                user_input, session_id, on_progress=_cli_progress
                            )
                        _print_agent_response(response, render_markdown=markdown)
                    except KeyboardInterrupt:
                        _restore_terminal()
                        console.print("\nGoodbye!")
                        break
                    except EOFError:
                        _restore_terminal()
                        console.print("\nGoodbye!")
                        break
            finally:
                await agent_loop.close_mcp()

        asyncio.run(run_interactive())


# ============================================================================
# Channel Commands
# ============================================================================


channels_app = typer.Typer(help="Manage channels")
app.add_typer(channels_app, name="channels")


@channels_app.command("status")
def channels_status():
    """Show channel status."""
    from bao.config.loader import load_config

    config = load_config()

    table = Table(title="Channel Status")
    table.add_column("Channel", style="cyan")
    table.add_column("Enabled", style="green")
    table.add_column("Configuration", style="yellow")

    # WhatsApp
    wa = config.channels.whatsapp
    table.add_row("WhatsApp", "✓" if wa.enabled else "✗", wa.bridge_url)

    dc = config.channels.discord
    table.add_row("Discord", "✓" if dc.enabled else "✗", dc.gateway_url)

    # Feishu
    fs = config.channels.feishu
    fs_config = f"app_id: {fs.app_id[:10]}..." if fs.app_id else "[dim]not configured[/dim]"
    table.add_row("Feishu", "✓" if fs.enabled else "✗", fs_config)

    # Mochat
    mc = config.channels.mochat
    mc_base = mc.base_url or "[dim]not configured[/dim]"
    table.add_row("Mochat", "✓" if mc.enabled else "✗", mc_base)

    # Telegram
    tg = config.channels.telegram
    tg_config = f"token: {tg.token[:10]}..." if tg.token else "[dim]not configured[/dim]"
    table.add_row("Telegram", "✓" if tg.enabled else "✗", tg_config)

    # Slack
    slack = config.channels.slack
    slack_config = "socket" if slack.app_token and slack.bot_token else "[dim]not configured[/dim]"
    table.add_row("Slack", "✓" if slack.enabled else "✗", slack_config)
    # DingTalk
    dt = config.channels.dingtalk
    dt_config = (
        f"client_id: {dt.client_id[:10]}..." if dt.client_id else "[dim]not configured[/dim]"
    )
    table.add_row("DingTalk", "✓" if dt.enabled else "✗", dt_config)

    # QQ
    qq = config.channels.qq
    qq_config = f"app_id: {qq.app_id[:10]}..." if qq.app_id else "[dim]not configured[/dim]"
    table.add_row("QQ", "✓" if qq.enabled else "✗", qq_config)

    # Email
    em = config.channels.email
    em_config = em.imap_host if em.imap_host else "[dim]not configured[/dim]"
    table.add_row("Email", "✓" if em.enabled else "✗", em_config)

    console.print(table)


def _get_bridge_dir() -> Path:
    """Get the bridge directory, setting it up if needed."""
    import shutil
    import subprocess

    # User's bridge location
    user_bridge = Path.home() / ".bao" / "bridge"

    # Check if already built
    if (user_bridge / "dist" / "index.js").exists():
        return user_bridge

    # Check for npm
    if not shutil.which("npm"):
        console.print("[red]npm not found. Please install Node.js >= 18.[/red]")
        raise typer.Exit(1)

    # Find source bridge: first check package data, then source dir
    pkg_bridge = Path(__file__).parent.parent / "bridge"  # bao/bridge (installed)
    src_bridge = Path(__file__).parent.parent.parent / "bridge"  # repo root/bridge (dev)

    source = None
    if (pkg_bridge / "package.json").exists():
        source = pkg_bridge
    elif (src_bridge / "package.json").exists():
        source = src_bridge

    if not source:
        console.print("[red]Bridge source not found.[/red]")
        console.print("Try reinstalling: pip install --force-reinstall bao")
        raise typer.Exit(1)

    console.print(f"{__logo__} Setting up bridge...")

    # Copy to user directory
    user_bridge.parent.mkdir(parents=True, exist_ok=True)
    if user_bridge.exists():
        shutil.rmtree(user_bridge)
    shutil.copytree(source, user_bridge, ignore=shutil.ignore_patterns("node_modules", "dist"))

    # Install and build
    try:
        console.print("  Installing dependencies...")
        subprocess.run(["npm", "install"], cwd=user_bridge, check=True, capture_output=True)

        console.print("  Building...")
        subprocess.run(["npm", "run", "build"], cwd=user_bridge, check=True, capture_output=True)

        console.print("[green]✓[/green] Bridge ready\n")
    except subprocess.CalledProcessError as e:
        console.print(f"[red]Build failed: {e}[/red]")
        if e.stderr:
            console.print(f"[dim]{e.stderr.decode()[:500]}[/dim]")
        raise typer.Exit(1)

    return user_bridge


@channels_app.command("login")
def channels_login():
    """Link device via QR code."""
    import subprocess
    from bao.config.loader import load_config

    config = load_config()
    bridge_dir = _get_bridge_dir()

    console.print(f"{__logo__} Starting bridge...")
    console.print("Scan the QR code to connect.\n")

    env = {**os.environ}
    if config.channels.whatsapp.bridge_token:
        env["BRIDGE_TOKEN"] = config.channels.whatsapp.bridge_token

    try:
        subprocess.run(["npm", "start"], cwd=bridge_dir, check=True, env=env)
    except subprocess.CalledProcessError as e:
        console.print(f"[red]Bridge failed: {e}[/red]")
    except FileNotFoundError:
        console.print("[red]npm not found. Please install Node.js.[/red]")


# ============================================================================
# Cron Commands
# ============================================================================

cron_app = typer.Typer(help="Manage scheduled tasks")
app.add_typer(cron_app, name="cron")


@cron_app.command("list")
def cron_list(
    all: bool = typer.Option(False, "--all", "-a", help="Include disabled jobs"),
):
    """List scheduled jobs."""
    from bao.config.loader import get_data_dir
    from bao.cron.service import CronService

    store_path = get_data_dir() / "cron" / "jobs.json"
    service = CronService(store_path)

    jobs = service.list_jobs(include_disabled=all)

    if not jobs:
        console.print("No scheduled jobs.")
        return

    table = Table(title="Scheduled Jobs")
    table.add_column("ID", style="cyan")
    table.add_column("Name")
    table.add_column("Schedule")
    table.add_column("Status")
    table.add_column("Next Run")

    import time
    from datetime import datetime as _dt
    from zoneinfo import ZoneInfo

    for job in jobs:
        # Format schedule
        if job.schedule.kind == "every":
            sched = f"every {(job.schedule.every_ms or 0) // 1000}s"
        elif job.schedule.kind == "cron":
            sched = (
                f"{job.schedule.expr or ''} ({job.schedule.tz})"
                if job.schedule.tz
                else (job.schedule.expr or "")
            )
        else:
            sched = "one-time"

        # Format next run
        next_run = ""
        if job.state.next_run_at_ms:
            ts = job.state.next_run_at_ms / 1000
            try:
                tz = ZoneInfo(job.schedule.tz) if job.schedule.tz else None
                next_run = _dt.fromtimestamp(ts, tz).strftime("%Y-%m-%d %H:%M")
            except Exception:
                next_run = time.strftime("%Y-%m-%d %H:%M", time.localtime(ts))

        status = "[green]enabled[/green]" if job.enabled else "[dim]disabled[/dim]"

        table.add_row(job.id, job.name, sched, status, next_run)

    console.print(table)


@cron_app.command("add")
def cron_add(
    name: str = typer.Option(..., "--name", "-n", help="Job name"),
    message: str = typer.Option(..., "--message", "-m", help="Message for agent"),
    every: int = typer.Option(None, "--every", "-e", help="Run every N seconds"),
    cron_expr: str = typer.Option(None, "--cron", "-c", help="Cron expression (e.g. '0 9 * * *')"),
    tz: str | None = typer.Option(
        None, "--tz", help="IANA timezone for cron (e.g. 'America/Vancouver')"
    ),
    at: str = typer.Option(None, "--at", help="Run once at time (ISO format)"),
    deliver: bool = typer.Option(False, "--deliver", "-d", help="Deliver response to channel"),
    to: str = typer.Option(None, "--to", help="Recipient for delivery"),
    channel: str = typer.Option(
        None, "--channel", help="Channel for delivery (e.g. 'telegram', 'whatsapp')"
    ),
):
    """Add a scheduled job."""
    from bao.config.loader import get_data_dir
    from bao.cron.service import CronService
    from bao.cron.types import CronSchedule

    if tz and not cron_expr:
        console.print("[red]Error: --tz can only be used with --cron[/red]")
        raise typer.Exit(1)

    # Determine schedule type
    if every:
        schedule = CronSchedule(kind="every", every_ms=every * 1000)
    elif cron_expr:
        schedule = CronSchedule(kind="cron", expr=cron_expr, tz=tz)
    elif at:
        import datetime

        dt = datetime.datetime.fromisoformat(at)
        schedule = CronSchedule(kind="at", at_ms=int(dt.timestamp() * 1000))
    else:
        console.print("[red]Error: Must specify --every, --cron, or --at[/red]")
        raise typer.Exit(1)

    store_path = get_data_dir() / "cron" / "jobs.json"
    service = CronService(store_path)

    try:
        job = service.add_job(
            name=name,
            schedule=schedule,
            message=message,
            deliver=deliver,
            to=to,
            channel=channel,
        )
    except ValueError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1) from e

    console.print(f"[green]✓[/green] Added job '{job.name}' ({job.id})")


@cron_app.command("remove")
def cron_remove(
    job_id: str = typer.Argument(..., help="Job ID to remove"),
):
    """Remove a scheduled job."""
    from bao.config.loader import get_data_dir
    from bao.cron.service import CronService

    store_path = get_data_dir() / "cron" / "jobs.json"
    service = CronService(store_path)

    if service.remove_job(job_id):
        console.print(f"[green]✓[/green] Removed job {job_id}")
    else:
        console.print(f"[red]Job {job_id} not found[/red]")


@cron_app.command("enable")
def cron_enable(
    job_id: str = typer.Argument(..., help="Job ID"),
    disable: bool = typer.Option(False, "--disable", help="Disable instead of enable"),
):
    """Enable or disable a job."""
    from bao.config.loader import get_data_dir
    from bao.cron.service import CronService

    store_path = get_data_dir() / "cron" / "jobs.json"
    service = CronService(store_path)

    job = service.enable_job(job_id, enabled=not disable)
    if job:
        status = "disabled" if disable else "enabled"
        console.print(f"[green]✓[/green] Job '{job.name}' {status}")
    else:
        console.print(f"[red]Job {job_id} not found[/red]")


@cron_app.command("run")
def cron_run(
    job_id: str = typer.Argument(..., help="Job ID to run"),
    force: bool = typer.Option(False, "--force", "-f", help="Run even if disabled"),
):
    """Manually run a job."""
    from loguru import logger
    from bao.config.loader import load_config, get_data_dir
    from bao.cron.service import CronService
    from bao.cron.types import CronJob
    from bao.bus.queue import MessageBus
    from bao.agent.loop import AgentLoop

    logger.disable("bao")
    config = load_config()
    provider = _make_provider(config)
    bus = MessageBus()
    agent_loop = AgentLoop(
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
        embedding_config=config.tools.embedding,
        restrict_to_workspace=config.tools.restrict_to_workspace,
        mcp_servers=config.tools.mcp_servers,
        available_models=config.agents.defaults.models,
        config=config,
    )
    store_path = get_data_dir() / "cron" / "jobs.json"
    service = CronService(store_path)
    result_holder = []

    async def on_job(job: CronJob) -> str | None:
        response = await agent_loop.process_direct(
            job.payload.message,
            session_key=f"cron:{job.id}",
            channel=job.payload.channel or "cli",
            chat_id=job.payload.to or "direct",
        )
        result_holder.append(response)
        return response

    service.on_job = on_job

    async def run():
        return await service.run_job(job_id, force=force)

    if asyncio.run(run()):
        console.print("[green]\u2713[/green] Job executed")
        if result_holder:
            _print_agent_response(result_holder[0], render_markdown=True)
    else:
        console.print(f"[red]Failed to run job {job_id}[/red]")


# ============================================================================
# OAuth Login
# ============================================================================

provider_app = typer.Typer(help="Manage providers")
app.add_typer(provider_app, name="provider")


_LOGIN_HANDLERS: dict[str, callable] = {}


def _register_login(name: str):
    def decorator(fn):
        _LOGIN_HANDLERS[name] = fn
        return fn

    return decorator


@provider_app.command("login")
def provider_login(
    provider: str = typer.Argument(
        ..., help="OAuth provider (e.g. 'openai-codex', 'github-copilot')"
    ),
):
    """Authenticate with an OAuth provider."""
    from bao.providers.registry import PROVIDERS, ProviderType

    key = provider.replace("-", "_")
    spec = next(
        (s for s in PROVIDERS if s.name == key and s.provider_type == ProviderType.OAUTH), None
    )
    if not spec:
        names = ", ".join(
            s.name.replace("_", "-") for s in PROVIDERS if s.provider_type == ProviderType.OAUTH
        )
        console.print(f"[red]Unknown OAuth provider: {provider}[/red]  Supported: {names}")
        raise typer.Exit(1)

    handler = _LOGIN_HANDLERS.get(spec.name)
    if not handler:
        console.print(f"[red]Login not implemented for {spec.display_name}[/red]")
        raise typer.Exit(1)

    console.print(f"{__logo__} OAuth Login - {spec.display_name}\n")
    handler()


@_register_login("openai_codex")
def _login_openai_codex() -> None:
    try:
        from oauth_cli_kit import get_token, login_oauth_interactive

        token = None
        try:
            token = get_token()
        except Exception:
            pass
        if not (token and token.access):
            console.print("[cyan]Starting interactive OAuth login...[/cyan]\n")
            token = login_oauth_interactive(
                print_fn=lambda s: console.print(s),
                prompt_fn=lambda s: typer.prompt(s),
            )
        if not (token and token.access):
            console.print("[red]✗ Authentication failed[/red]")
            raise typer.Exit(1)
        console.print(
            f"[green]✓ Authenticated with OpenAI Codex[/green]  [dim]{token.account_id}[/dim]"
        )
    except ImportError:
        console.print("[red]oauth_cli_kit not installed. Run: pip install oauth-cli-kit[/red]")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
