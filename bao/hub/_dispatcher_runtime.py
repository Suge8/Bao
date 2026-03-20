from __future__ import annotations

from time import perf_counter_ns

from bao.hub._dispatcher_models import HubAutomationBundle, HubRuntimeBundle
from bao.hub._observability import elapsed_ms, record_dispatch_observation
from bao.hub._route_resolution import RouteResolutionResult, SessionOrigin

from ._dispatcher_inputs import normalize_profile_id


class HubDispatcherRuntimeMixin:
    def _current_runtime_bundle(self) -> HubRuntimeBundle | None:
        profile_id = self._normalize_target_profile(self._current_profile_id)
        if not profile_id:
            return None
        return self._runtime_cache.get(profile_id)

    def _current_automation_bundle(self) -> HubAutomationBundle | None:
        profile_id = self._normalize_target_profile(self._current_profile_id)
        if not profile_id:
            return None
        return self._ensure_automation(profile_id)

    def _resolve_runtime_bundle(
        self,
        *,
        request_kind: str,
        explicit_profile_id: object,
        session_key: object,
        origin: SessionOrigin,
    ) -> tuple[RouteResolutionResult, HubRuntimeBundle]:
        route_started_ns = perf_counter_ns()
        resolution = self._route_resolver.resolve(
            explicit_profile_id=explicit_profile_id,
            session_key=session_key,
            origin=origin,
        )
        route_resolve_ms = elapsed_ms(route_started_ns)
        runtime_profile_id = self._normalize_target_profile(resolution.profile_id)
        runtime_cached = runtime_profile_id in self._runtime_cache
        runtime_started_ns = perf_counter_ns()
        runtime = self._ensure_runtime(runtime_profile_id)
        runtime_load_ms = elapsed_ms(runtime_started_ns)
        record_dispatch_observation(
            request_kind=request_kind,
            resolution=resolution,
            runtime_cached=runtime_cached,
            route_resolve_ms=route_resolve_ms,
            runtime_load_ms=runtime_load_ms,
        )
        return resolution, runtime

    def _service_profile_ids(self) -> tuple[str, ...]:
        if self._known_profile_ids:
            return self._known_profile_ids
        profile_id = self._normalize_target_profile(self._current_profile_id)
        return (profile_id,) if profile_id else ("",)

    def _ensure_runtime(self, profile_id: object) -> HubRuntimeBundle:
        normalized = self._normalize_target_profile(profile_id)
        cached = self._runtime_cache.get(normalized)
        if cached is not None:
            return cached
        runtime = self._runtime_loader(normalized)
        self._runtime_cache[runtime.profile_id] = runtime
        return runtime

    def _ensure_automation(self, profile_id: object) -> HubAutomationBundle:
        normalized = self._normalize_target_profile(profile_id)
        cached = self._automation_cache.get(normalized)
        if cached is not None:
            return cached
        automation = self._automation_loader(normalized)
        self._automation_cache[automation.profile_id] = automation
        return automation

    def _remember_route(self, session_key: object, origin: SessionOrigin, profile_id: object) -> None:
        self._route_resolver.remember(session_key=session_key, origin=origin, profile_id=profile_id)

    def _normalize_target_profile(self, profile_id: object) -> str:
        normalized = normalize_profile_id(profile_id)
        if normalized:
            return normalized
        if self._default_profile_id:
            return self._default_profile_id
        return ""
