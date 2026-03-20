from __future__ import annotations

from time import perf_counter_ns
from typing import Any

from bao.runtime_diagnostics import get_runtime_diagnostics_store
from bao.runtime_diagnostics_models import RuntimeEventRequest

from ._route_resolution import RouteResolutionResult

OBSERVABILITY_SOURCE = "hub_dispatch"
ROUTE_PREWARM_CODE = "hub_route_state_prewarm"
ROUTE_OBSERVED_CODE = "hub_route_observed"
_INTERESTING_ROUTE_SOURCES = frozenset({"channel_binding", "default_profile"})


def elapsed_ms(start_ns: int) -> float:
    return round((perf_counter_ns() - start_ns) / 1_000_000, 3)


def record_route_state_prewarm(
    *,
    route_index: Any,
    channel_bindings: Any,
) -> dict[str, Any]:
    route_started_ns = perf_counter_ns()
    route_snapshot = route_index.snapshot()
    route_load_ms = elapsed_ms(route_started_ns)

    binding_started_ns = perf_counter_ns()
    binding_snapshot = channel_bindings.snapshot()
    binding_load_ms = elapsed_ms(binding_started_ns)

    details = {
        "route_entries": len(route_snapshot),
        "channel_binding_entries": len(binding_snapshot),
        "route_index_load_ms": route_load_ms,
        "channel_binding_load_ms": binding_load_ms,
        "prewarm_total_ms": round(route_load_ms + binding_load_ms, 3),
    }
    _record_event(
        stage="startup",
        message="Hub route state prewarmed",
        level="info",
        code=ROUTE_PREWARM_CODE,
        details=details,
    )
    return details


def record_dispatch_observation(
    *,
    request_kind: str,
    resolution: RouteResolutionResult,
    runtime_cached: bool,
    route_resolve_ms: float,
    runtime_load_ms: float,
) -> None:
    if runtime_cached and resolution.source not in _INTERESTING_ROUTE_SOURCES:
        return
    details = resolution.as_snapshot()
    details.update(
        {
            "request_kind": request_kind,
            "runtime_cached": runtime_cached,
            "route_resolve_ms": route_resolve_ms,
            "runtime_load_ms": runtime_load_ms,
            "prepare_total_ms": round(route_resolve_ms + runtime_load_ms, 3),
        }
    )
    _record_event(
        stage="dispatch",
        message=_dispatch_message(
            request_kind=request_kind,
            resolution=resolution,
            runtime_cached=runtime_cached,
        ),
        level="warning" if resolution.source == "default_profile" else "info",
        code=ROUTE_OBSERVED_CODE,
        session_key=resolution.session_key,
        details=details,
    )


def _dispatch_message(
    *,
    request_kind: str,
    resolution: RouteResolutionResult,
    runtime_cached: bool,
) -> str:
    if not runtime_cached and resolution.source == "default_profile":
        return (
            f"Hub cold-start fell back to default profile '{resolution.profile_id}' "
            f"for {request_kind}"
        )
    if not runtime_cached:
        return (
            f"Hub cold-start loaded profile '{resolution.profile_id}' "
            f"via {resolution.source} for {request_kind}"
        )
    if resolution.source == "default_profile":
        return f"Hub route miss fell back to default profile '{resolution.profile_id}'"
    return f"Hub reused {resolution.source} for {request_kind}"


def _record_event(
    *,
    stage: str,
    message: str,
    level: str,
    code: str,
    details: dict[str, Any],
    session_key: str = "",
) -> None:
    get_runtime_diagnostics_store().record_event(
        RuntimeEventRequest(
            source=OBSERVABILITY_SOURCE,
            stage=stage,
            message=message,
            level=level,
            code=code,
            session_key=session_key,
            details=details,
        )
    )
