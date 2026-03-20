from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from bao.session.manager import SessionManager

from .control import HubControl, local_hub_control
from .directory import HubDirectory
from .runtime import HubRuntimePort


@dataclass(frozen=True, slots=True)
class HubLocalPorts:
    state_root: Path
    directory: HubDirectory
    control: HubControl
    runtime: HubRuntimePort


def open_local_hub_ports(state_root: str | Path) -> HubLocalPorts:
    root = Path(str(state_root)).expanduser()
    session_manager = SessionManager(root)
    return HubLocalPorts(
        state_root=root,
        directory=HubDirectory(session_manager),
        control=local_hub_control(session_manager=session_manager),
        runtime=HubRuntimePort(session_manager),
    )
