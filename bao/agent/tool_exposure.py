from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ToolExposureSnapshot:
    mode: str
    force_final_response: bool
    route_text: str
    enabled_domains: tuple[str, ...] = ()
    selected_domains: tuple[str, ...] = ()
    ordered_tool_names: tuple[str, ...] = ()
    available_tool_lines: tuple[str, ...] = ()
    tool_definitions: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    full_exposure: bool = False
    slim_schema: bool = False

    def allowed_tool_names(self) -> set[str] | None:
        if self.full_exposure:
            return None
        return set(self.ordered_tool_names)

    def as_record(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "force_final_response": self.force_final_response,
            "route_text": self.route_text,
            "enabled_domains": list(self.enabled_domains),
            "selected_domains": list(self.selected_domains),
            "ordered_tool_names": list(self.ordered_tool_names),
            "available_tool_lines": list(self.available_tool_lines),
            "tool_definition_count": len(self.tool_definitions),
            "full_exposure": self.full_exposure,
            "slim_schema": self.slim_schema,
        }
