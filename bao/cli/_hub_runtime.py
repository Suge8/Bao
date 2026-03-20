from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class HubRunOptions:
    port: int | None
    verbose: bool
    config_path: str | None = None
    workspace: str | None = None


@dataclass(frozen=True)
class HubBackgroundRunRequest:
    stack: Any
    send_startup_greeting: Any
    startup_options: Any
    on_keyboard_interrupt: Any


def coerce_hub_run_options(
    *,
    options: HubRunOptions | None,
    legacy_kwargs: dict[str, object],
) -> HubRunOptions:
    if options is not None:
        if legacy_kwargs:
            unknown = ", ".join(sorted(legacy_kwargs))
            raise TypeError(f"Unsupported hub kwargs with options: {unknown}")
        return options
    return _options_from_legacy_kwargs(legacy_kwargs)


def _options_from_legacy_kwargs(legacy_kwargs: dict[str, object]) -> HubRunOptions:
    raw = dict(legacy_kwargs)
    unsupported = sorted(set(raw) - {"port", "verbose", "config_path", "workspace"})
    if unsupported:
        unknown = ", ".join(unsupported)
        raise TypeError(f"Unsupported hub kwargs: {unknown}")
    if "verbose" not in raw:
        raise TypeError("Missing required argument: verbose")
    verbose = bool(raw.pop("verbose"))
    port = raw.pop("port", None)
    config_path = raw.pop("config_path", None)
    workspace = raw.pop("workspace", None)
    return HubRunOptions(
        port=port if isinstance(port, int) or port is None else int(port),
        verbose=verbose,
        config_path=str(config_path) if config_path is not None else None,
        workspace=str(workspace) if workspace is not None else None,
    )


def resolve_effective_port(port: int | None, config_port: object) -> int:
    if isinstance(port, int):
        return port
    return int(config_port)


async def run_hub_background(request: HubBackgroundRunRequest) -> None:
    try:
        await _run_hub_tasks(request)
    except KeyboardInterrupt:
        request.on_keyboard_interrupt()
    finally:
        await _shutdown_hub_stack(request.stack)


async def _run_hub_tasks(request: HubBackgroundRunRequest) -> None:
    import asyncio

    await asyncio.gather(
        request.stack.dispatcher.run(),
        request.stack.channels.start_all(),
        request.send_startup_greeting(
            request.stack.agent,
            request.stack.bus,
            request.startup_options,
        ),
    )


async def _shutdown_hub_stack(stack: Any) -> None:
    await stack.dispatcher.close_mcp()
    stack.dispatcher.stop()
    await stack.channels.stop_all()
