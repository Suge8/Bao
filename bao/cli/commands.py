from __future__ import annotations

import asyncio
import sys
from typing import TYPE_CHECKING

import typer
from rich.console import Console

from bao import __logo__, __version__
from bao.cli._banner_runtime import (
    BannerImageOverlay,
    StartupBanner,
    StartupBannerBuildOptions,
    StartupScreenBuildOptions,
    StartupScreenModel,
    build_startup_banner,
    build_startup_screen_model,
    count_available_skills,
    detect_terminal_image_protocol,
    emit_banner_overlay,
)
from bao.cli._hub_runtime import (
    HubBackgroundRunRequest,
    HubRunOptions,
    coerce_hub_run_options,
    resolve_effective_port,
    run_hub_background,
)

if TYPE_CHECKING:
    from bao.config.schema import Config

app = typer.Typer(name="bao", help=f"{__logo__} Bao - 中枢", invoke_without_command=True)
console = Console()


def _build_startup_screen_model(options: StartupScreenBuildOptions) -> StartupScreenModel:
    return build_startup_screen_model(options)


def _detect_terminal_image_protocol() -> str | None:
    return detect_terminal_image_protocol(console)


def _build_startup_banner(model: StartupScreenModel, *, width: int) -> StartupBanner:
    return build_startup_banner(
        StartupBannerBuildOptions(model=model, width=width, detect_protocol=_detect_terminal_image_protocol)
    )


def _emit_banner_overlay(overlay: BannerImageOverlay) -> None:
    emit_banner_overlay(console, overlay)


def _print_startup_screen(model: StartupScreenModel) -> None:
    banner = _build_startup_banner(model, width=console.size.width)
    console.print()
    console.print(banner.renderable)
    if banner.overlay:
        _emit_banner_overlay(banner.overlay)
    console.print()


def version_callback(value: bool) -> None:
    if value:
        console.print(f"{__logo__} Bao v{__version__}")
        raise typer.Exit()


def _collect_search_providers(config: Config) -> list[str]:
    search = config.tools.web.search
    providers = [
        name
        for name, enabled in (
            ("tavily", bool(search.tavily_api_key.get_secret_value())),
            ("brave", bool(search.brave_api_key.get_secret_value())),
            ("exa", bool(search.exa_api_key.get_secret_value())),
        )
        if enabled
    ]
    return providers


def _make_provider(config: Config):
    from bao.providers import make_provider

    try:
        return make_provider(config)
    except ValueError as exc:
        from bao.config.loader import get_config_path

        console.print(f"\n[yellow]⚠ {exc}[/yellow]")
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
        return

    def _friendly_format(record):
        lvl = record["level"].name
        if lvl == "WARNING":
            return "{time:HH:mm:ss} │ <yellow>{message}</yellow>\n{exception}"
        if lvl in ("ERROR", "CRITICAL"):
            return "{time:HH:mm:ss} │ <red>{message}</red>\n{exception}"
        return "{time:HH:mm:ss} │ {message}\n{exception}"

    logger.add(sys.stderr, level="INFO", format=_friendly_format)


def run_hub(*, options: HubRunOptions | None = None, **legacy_kwargs: object) -> None:
    from bao.config import set_runtime_config_path
    from bao.config.loader import load_config
    from bao.hub.builder import (
        BuildHubStackOptions,
        StartupGreetingOptions,
        build_hub_stack,
        send_startup_greeting,
    )
    from bao.profile import active_profile_context

    run_options = coerce_hub_run_options(options=options, legacy_kwargs=legacy_kwargs)
    _setup_logging(run_options.verbose)
    if run_options.config_path:
        set_runtime_config_path(run_options.config_path)
    config = load_config()
    if run_options.workspace:
        config.agents.defaults.workspace = run_options.workspace
    profile_ctx = active_profile_context(shared_workspace=config.workspace_path)
    provider = _make_provider(config)
    stack = build_hub_stack(config, provider, BuildHubStackOptions(profile_context=profile_ctx))
    cron_status = stack.cron.status()
    _print_startup_screen(
        _build_startup_screen_model(
            StartupScreenBuildOptions(
                port=resolve_effective_port(run_options.port, config.hub.port),
                enabled_channels=list(stack.channels.enabled_channels),
                cron_jobs=int(cron_status["jobs"]),
                heartbeat_interval_s=int(stack.heartbeat.interval_s),
                search_providers=_collect_search_providers(config),
                desktop_enabled=bool(config.tools.desktop.enabled),
                skills_count=count_available_skills(config.workspace_path),
            )
        )
    )
    startup_options = StartupGreetingOptions(
        config=stack.config,
        channels=stack.channels,
        session_manager=stack.session_manager,
        profile_context=profile_ctx,
    )
    asyncio.run(
        run_hub_background(
            HubBackgroundRunRequest(
                stack=stack,
                send_startup_greeting=send_startup_greeting,
                startup_options=startup_options,
                on_keyboard_interrupt=lambda: console.print("\n👋 正在关闭 / Shutting down..."),
            )
        )
    )


def _main_callback(options: HubRunOptions, *, version: bool) -> None:
    version_callback(version)
    run_hub(options=options)


def main(
    port: int | None = typer.Option(None, "--port", "-p", help="中枢端口"),
    workspace: str | None = typer.Option(None, "--workspace", "-w", help="工作区目录"),
    config: str | None = typer.Option(None, "--config", "-c", help="配置文件路径"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="输出详细日志"),
    version: bool = typer.Option(False, "--version", is_eager=True),
) -> None:
    _main_callback(
        HubRunOptions(port=port, verbose=verbose, config_path=config, workspace=workspace),
        version=version,
    )


app.callback()(main)


if __name__ == "__main__":
    app()
