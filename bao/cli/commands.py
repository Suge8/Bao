from __future__ import annotations

import asyncio
import sys
from typing import TYPE_CHECKING

import typer
from rich.console import Console

from bao import __logo__, __version__

if TYPE_CHECKING:
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


def run_gateway(port: int, verbose: bool) -> None:
    from bao.config.loader import load_config
    from bao.gateway.builder import build_gateway_stack, send_startup_greeting

    _setup_logging(verbose)

    if not isinstance(port, int):
        port = 18790
    console.print(f"\n{__logo__} 启动 bao 网关 / Starting bao gateway on port {port}...")

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
                send_startup_greeting(stack.agent, stack.bus, stack.config),
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
