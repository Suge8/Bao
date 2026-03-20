from __future__ import annotations

from dataclasses import dataclass

from bao.__about__ import __logo__


@dataclass(frozen=True)
class CoreCommandSpec:
    name: str
    description: str
    visible_in_help: bool = True
    visible_in_telegram_menu: bool = True
    handled_by_core: bool = True

    @property
    def slash_name(self) -> str:
        return f"/{self.name}"

    @property
    def help_line(self) -> str:
        return f"{self.slash_name} — {self.description}"


CORE_COMMAND_SPECS: tuple[CoreCommandSpec, ...] = (
    CoreCommandSpec("start", "Start the bot", visible_in_help=False, handled_by_core=False),
    CoreCommandSpec("new", "Start a new conversation"),
    CoreCommandSpec("stop", "Stop the current task"),
    CoreCommandSpec("session", "Switch between conversations"),
    CoreCommandSpec("delete", "Delete current conversation"),
    CoreCommandSpec("model", "Switch model"),
    CoreCommandSpec("memory", "Manage long-term memory"),
    CoreCommandSpec("help", "Show available commands"),
)

_CORE_COMMANDS_BY_NAME = {spec.name: spec for spec in CORE_COMMAND_SPECS}
_HELP_COMMAND_SPECS = tuple(spec for spec in CORE_COMMAND_SPECS if spec.visible_in_help)
_TELEGRAM_COMMAND_SPECS = tuple(spec for spec in CORE_COMMAND_SPECS if spec.visible_in_telegram_menu)
_TELEGRAM_FORWARD_COMMAND_NAMES = tuple(spec.name for spec in CORE_COMMAND_SPECS if spec.handled_by_core)


def build_help_text() -> str:
    help_lines = [spec.help_line for spec in _HELP_COMMAND_SPECS]
    return f"{__logo__} Bao commands:\n" + "\n".join(help_lines)


def extract_command_name(text: str) -> str | None:
    raw = text.strip().lower()
    if not raw.startswith("/"):
        return None
    token = raw.split(maxsplit=1)[0]
    command_name = token[1:]
    if not command_name:
        return None
    spec = _CORE_COMMANDS_BY_NAME.get(command_name)
    if spec is None or not spec.handled_by_core:
        return None
    return command_name


def iter_telegram_command_specs() -> tuple[CoreCommandSpec, ...]:
    return _TELEGRAM_COMMAND_SPECS


def iter_telegram_forward_command_names() -> tuple[str, ...]:
    return _TELEGRAM_FORWARD_COMMAND_NAMES


def format_new_session_started(name: str) -> str:
    return f"好的，新对话开始啦「{name}」 {__logo__}"
