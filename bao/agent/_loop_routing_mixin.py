from __future__ import annotations

from typing import Any

from bao.agent._tool_exposure_domains import TOOL_DOMAIN_CODING as _TOOL_DOMAIN_CODING
from bao.agent._tool_exposure_domains import TOOL_DOMAIN_CORE as _TOOL_DOMAIN_CORE
from bao.agent._tool_exposure_domains import TOOL_DOMAIN_DESKTOP as _TOOL_DOMAIN_DESKTOP
from bao.agent._tool_exposure_domains import TOOL_DOMAIN_HANDOFF as _TOOL_DOMAIN_HANDOFF
from bao.agent._tool_exposure_domains import TOOL_DOMAIN_MESSAGING as _TOOL_DOMAIN_MESSAGING
from bao.agent._tool_exposure_domains import ordered_required_tools as _ordered_required_tools
from bao.agent._tool_exposure_ranker import select_domains_by_bm25
from bao.agent.capability_registry import build_available_tool_lines
from bao.agent.tool_exposure import ToolExposureSnapshot


class LoopRoutingMixin:
    def _required_tool_names_for_domains(self, selected_domains: set[str]) -> set[str]:
        ordered = _ordered_required_tools(selected_domains, set(self.tools.tool_names))
        return {
            name
            for name in ordered
            if (meta := self.tools.get_metadata(name)) is not None and meta.auto_callable
        }

    def _select_tool_names_for_turn(
        self,
        initial_messages: list[dict[str, Any]],
        extra_signal_text: str | None = None,
    ) -> set[str] | None:
        if self._tool_exposure_mode == "off":
            return None
        user_text = self._build_tool_route_text(initial_messages, extra_signal_text)
        selected_domains = self._selected_domains_for_route_text(user_text)
        selected = self._required_tool_names_for_domains(selected_domains)
        if selected:
            return selected
        return self._required_tool_names_for_domains({_TOOL_DOMAIN_CORE})

    def _selected_domains_for_route_text(self, user_text: str) -> set[str]:
        selected = select_domains_by_bm25(
            query=user_text,
            enabled_domains=self._tool_exposure_domains,
        ).selected_domains
        if (
            _TOOL_DOMAIN_MESSAGING in selected
            and _TOOL_DOMAIN_HANDOFF in self._tool_exposure_domains
        ):
            selected.add(_TOOL_DOMAIN_HANDOFF)
        if (
            self._has_desktop_override_signal(user_text)
            and _TOOL_DOMAIN_DESKTOP in self._tool_exposure_domains
        ):
            selected.add(_TOOL_DOMAIN_DESKTOP)
        if self._has_code_path_signal(user_text):
            selected.add(_TOOL_DOMAIN_CORE)
            if _TOOL_DOMAIN_CODING in self._tool_exposure_domains:
                selected.add(_TOOL_DOMAIN_CODING)
        return selected or ({_TOOL_DOMAIN_CORE} & self._tool_exposure_domains)

    def _order_selected_tool_names(
        self,
        selected_tool_names: set[str] | None,
        user_text: str,
    ) -> list[str]:
        if not selected_tool_names:
            return []
        domains = self._selected_domains_for_route_text(user_text)
        return _ordered_required_tools(domains, set(selected_tool_names))

    def _apply_available_tools_to_messages(
        self,
        messages: list[dict[str, Any]],
        selected_tool_names: list[str],
    ) -> list[dict[str, Any]]:
        if not messages:
            return messages
        first = messages[0]
        content = first.get("content")
        if first.get("role") != "system" or not isinstance(content, str):
            return messages
        first["content"] = self.context.apply_available_tools_block(
            content,
            build_available_tool_lines(registry=self.tools, selected_tool_names=selected_tool_names),
        )
        return messages

    def _build_tool_exposure_snapshot(
        self,
        *,
        initial_messages: list[dict[str, Any]],
        tool_signal_text: str | None,
        force_final_response: bool,
    ) -> ToolExposureSnapshot:
        route_text = self._build_tool_route_text(initial_messages, tool_signal_text)
        enabled_domains = tuple(sorted(self._tool_exposure_domains))
        selected_domains = tuple(sorted(self._selected_domains_for_route_text(route_text)))
        if force_final_response:
            return ToolExposureSnapshot(
                mode=self._tool_exposure_mode,
                force_final_response=True,
                route_text=route_text,
                enabled_domains=enabled_domains,
                selected_domains=selected_domains,
            )
        selected_tool_names = self._select_tool_names_for_turn(
            initial_messages,
            extra_signal_text=tool_signal_text,
        )
        ordered_tool_names = tuple(self._order_selected_tool_names(selected_tool_names, route_text))
        tool_definitions, slim_schema = self.tools.get_budgeted_definitions(names=selected_tool_names)
        available_lines = tuple(
            build_available_tool_lines(
                registry=self.tools,
                selected_tool_names=list(ordered_tool_names),
            )
        )
        return ToolExposureSnapshot(
            mode=self._tool_exposure_mode,
            force_final_response=False,
            route_text=route_text,
            enabled_domains=enabled_domains,
            selected_domains=selected_domains,
            ordered_tool_names=ordered_tool_names,
            available_tool_lines=available_lines,
            tool_definitions=tuple(tool_definitions),
            full_exposure=selected_tool_names is None,
            slim_schema=slim_schema,
        )
