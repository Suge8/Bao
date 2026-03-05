from __future__ import annotations

import asyncio
import sys
from typing import TYPE_CHECKING

import typer
from rich.console import Console
from rich.text import Text

from bao import __logo__, __version__

if TYPE_CHECKING:
    from bao.config.schema import Config

app = typer.Typer(name="bao", help=f"{__logo__} Bao - Gateway", invoke_without_command=True)
console = Console()

_BREAD = [
    "           [yellow]██████████[/]",
    "        [yellow]██▓▓▓▓▓▓▓▓▓▓▓▓██[/]",
    "      [yellow]██▓▓▓▓[/]●[yellow]▓▓▓▓▓▓[/]●[yellow]▓▓▓▓██[/]",
    "      [yellow]██▓▓▓▓▓▓▓[/]◡◡[yellow]▓▓▓▓▓▓▓██[/]",
    "        [yellow]██▓▓▓▓▓▓▓▓▓▓▓▓██[/]",
    "           [yellow]██████████[/]",
]
_BAO = r"""
  ██████╗  █████╗  ██████╗
  ██╔══██╗██╔══██╗██╔═══██╗
  ██████╔╝███████║██║   ██║
  ██╔══██╗██╔══██║██║   ██║
  ██████╔╝██║  ██║╚██████╔╝
  ╚═════╝ ╚═╝  ╚═╝ ╚═════╝"""


def _print_banner(port: int) -> None:
    console.print()
    for line in _BREAD:
        console.print(line)
    console.print(Text(_BAO, style="bold cyan"), highlight=False)
    console.print()
    console.print(f"  [dim]v{__version__}[/dim]  [italic dim]记忆 · 经验 · 进化[/italic dim]")
    console.print(f"  [dim]port {port}[/dim]")
    console.print()


def version_callback(value: bool) -> None:
    if value:
        console.print(f"{__logo__} Bao v{__version__}")
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

        def _friendly_format(record):
            lvl = record["level"].name
            if lvl == "WARNING":
                return "{time:HH:mm:ss} │ <yellow>{message}</yellow>\n{exception}"
            if lvl in ("ERROR", "CRITICAL"):
                return "{time:HH:mm:ss} │ <red>{message}</red>\n{exception}"
            return "{time:HH:mm:ss} │ {message}\n{exception}"

        logger.add(sys.stderr, level="INFO", format=_friendly_format)


def run_gateway(port: int, verbose: bool) -> None:
    from bao.config.loader import load_config
    from bao.gateway.builder import build_gateway_stack, send_startup_greeting

    _setup_logging(verbose)

    if not isinstance(port, int):
        port = 18790
    _print_banner(port)

    config = load_config()
    provider = _make_provider(config)
    stack = build_gateway_stack(config, provider)
    if stack.channels.enabled_channels:
        console.print(f"  📡 已启用通道 / Channels: {', '.join(stack.channels.enabled_channels)}")
    else:
        console.print("  [yellow]📡 未启用任何通道 / No channels enabled[/yellow]")

    cron_status = stack.cron.status()
    if cron_status["jobs"] > 0:
        console.print(f"  ⏰ 定时任务 / Cron: {cron_status['jobs']} jobs")
    console.print(f"  💓 心跳检查 / Heartbeat: every {stack.heartbeat.interval_s}s")

    async def run() -> None:
        try:
            await stack.cron.start()
            await stack.heartbeat.start()
            await asyncio.gather(
                stack.agent.run(),
                stack.channels.start_all(),
                send_startup_greeting(
                    stack.agent, stack.bus, stack.config, channels=stack.channels
                ),
            )
        except KeyboardInterrupt:
            console.print("\n👋 正在关闭 / Shutting down...")
        finally:
            await stack.agent.close_mcp()
            stack.heartbeat.stop()
            stack.cron.stop()
            stack.agent.stop()
            await stack.channels.stop_all()

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
