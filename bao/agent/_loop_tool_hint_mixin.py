from __future__ import annotations

import re
import shlex
from typing import Any
from urllib.parse import urlsplit

from bao.agent import plan as plan_state
from bao.agent import shared

from ._loop_constants import TOOL_HINT_CRON_ACTIONS as _TOOL_HINT_CRON_ACTIONS
from ._loop_constants import TOOL_HINT_ICONS as _TOOL_HINT_ICONS
from ._loop_constants import TOOL_HINT_LABELS as _TOOL_HINT_LABELS


class LoopToolHintMixin:
    @staticmethod
    def _strip_think(text: str | None) -> str | None:
        return shared.strip_think_tags(text)

    @staticmethod
    def _short_hint_arg(value: str, max_len: int = 72) -> str:
        text = value.strip().replace("\n", " ")
        if not text:
            return ""
        if text.startswith(("http://", "https://")):
            parts = urlsplit(text)
            host = parts.netloc.removeprefix("www.")
            segments = [seg for seg in parts.path.split("/") if seg]
            if not segments:
                return host
            if len(segments) == 1:
                compact = f"{host}/{segments[0]}"
            elif len(segments) == 2:
                compact = f"{host}/{segments[0]}/{segments[1]}"
            else:
                compact = f"{host}/{segments[0]}/.../{segments[-1]}"
            if len(compact) <= max_len:
                return compact
            keep = max(8, max_len - len(host) - 2)
            return f"{host}/{segments[0][:keep]}..."
        if len(text) <= max_len:
            return text
        cut = text[: max_len - 1]
        split_at = max(cut.rfind(" "), cut.rfind("/"), cut.rfind("_"), cut.rfind("-"))
        return f"{cut[:split_at]}..." if split_at >= 16 else f"{cut}..."

    @staticmethod
    def _tool_hint_normalized_name(raw_name: str) -> str:
        text = raw_name.strip()
        if not text:
            return ""
        return text.rsplit("__", 1)[-1] if "__" in text else text

    @classmethod
    def _tool_hint_label(cls, raw_name: str, hint_lang: str) -> str:
        name = cls._tool_hint_normalized_name(raw_name)
        if not name:
            return "工具" if hint_lang == "zh" else "Tool"
        label = _TOOL_HINT_LABELS.get(name)
        if label:
            return label[0] if hint_lang == "zh" else label[1]
        parts = [part for part in re.split(r"[_./-]+", name) if part]
        special = {"json": "JSON", "mcp": "MCP", "api": "API", "ui": "UI", "id": "ID"}
        return " ".join(special.get(part.lower(), part.capitalize()) for part in parts) or name

    @classmethod
    def _tool_hint_icon(cls, raw_name: str) -> str:
        name = cls._tool_hint_normalized_name(raw_name)
        icon = _TOOL_HINT_ICONS.get(name)
        if icon:
            return icon
        if any(token in name for token in ("search", "find", "lookup")):
            return "🔎"
        if any(token in name for token in ("fetch", "browser", "http", "url", "web")):
            return "🌐"
        if any(token in name for token in ("read", "file", "open")):
            return "📄"
        if any(token in name for token in ("write", "edit", "patch", "update")):
            return "📝"
        if any(token in name for token in ("list", "dir", "folder")):
            return "📁"
        if any(token in name for token in ("command", "shell", "exec", "bash")):
            return "💻"
        if any(token in name for token in ("plan", "task", "status")):
            return "📋"
        if any(token in name for token in ("memory", "remember", "forget")):
            return "🧠"
        if any(token in name for token in ("screen", "click", "drag", "scroll", "key", "type")):
            return "🖥️"
        return "🛠️"

    @staticmethod
    def _tool_hint_first_string(args: dict[str, Any], *keys: str) -> str:
        for key in keys:
            value = args.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ""

    @classmethod
    def _tool_hint_preview(cls, value: str, *, max_len: int = 20) -> str:
        text = value.strip().replace("\n", " ").replace("\r", " ")
        if not text:
            return ""
        return cls._short_hint_arg(text, max_len=max_len)

    @classmethod
    def _tool_hint_short_command(cls, value: str) -> str:
        text = value.strip()
        if not text:
            return ""
        try:
            tokens = shlex.split(text)
        except ValueError:
            tokens = text.split()
        while tokens and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", tokens[0]):
            tokens.pop(0)
        if not tokens:
            return cls._short_hint_arg(text, max_len=28)
        clipped: list[str] = []
        for token in tokens:
            if token in {"&&", "||", ";", "|"}:
                break
            clipped.append(token)
            if len(clipped) >= 3:
                break
        return cls._short_hint_arg(" ".join(clipped), max_len=28)

    @classmethod
    def _tool_hint_generic_detail(cls, args: dict[str, Any]) -> str:
        keys = (
            ("path", 48),
            ("url", 48),
            ("query", 32),
            ("action", 24),
            ("repo", 28),
            ("job_id", 24),
            ("source", 24),
            ("session_id", 24),
            ("session", 24),
            ("session_name", 24),
            ("agent", 18),
            ("category", 18),
        )
        for key, max_len in keys:
            safe_value = cls._tool_hint_first_string(args, key)
            if safe_value:
                return cls._short_hint_arg(safe_value, max_len=max_len)
        return ""

    @classmethod
    def _tool_hint_detail(cls, name: str, args: dict[str, Any], hint_lang: str) -> str:
        if not args:
            return ""
        if name == "spawn":
            return cls._short_hint_arg(cls._tool_hint_first_string(args, "label"), max_len=32)
        if name == "send_to_session":
            target = cls._tool_hint_first_string(args, "session_ref")
            if target:
                target = cls._short_hint_arg(target, max_len=18)
            else:
                session_key = cls._tool_hint_first_string(args, "session_key")
                if session_key:
                    target = cls._short_hint_arg(session_key, max_len=24)
            preview = cls._tool_hint_preview(cls._tool_hint_first_string(args, "content"))
            if target and preview:
                return f"{target} · {preview}"
            if target:
                return target
            if preview:
                return preview
        if name in {"coding_agent", "coding_agent_details"}:
            return cls._short_hint_arg(cls._tool_hint_first_string(args, "agent"), max_len=18)
        if name == "exec":
            return cls._tool_hint_short_command(cls._tool_hint_first_string(args, "command"))
        if name == "cron":
            action = cls._tool_hint_first_string(args, "action")
            if not action:
                return ""
            mapped = _TOOL_HINT_CRON_ACTIONS.get(action.lower())
            return mapped[0] if mapped and hint_lang == "zh" else mapped[1] if mapped else cls._short_hint_arg(action, max_len=18)
        if name in {"remember", "update_memory"}:
            return cls._short_hint_arg(cls._tool_hint_first_string(args, "category"), max_len=18)
        if name == "forget":
            return cls._short_hint_arg(cls._tool_hint_first_string(args, "query"), max_len=28)
        if name == "agent_browser":
            return cls._short_hint_arg(cls._tool_hint_first_string(args, "action"), max_len=20)
        if name == "update_plan_step":
            step_index = args.get("step_index")
            if isinstance(step_index, int) and step_index > 0:
                return f"第{step_index}步" if hint_lang == "zh" else f"step {step_index}"
        if name in {"cancel_task", "check_tasks", "check_tasks_json"}:
            return cls._short_hint_arg(cls._tool_hint_first_string(args, "task_id"), max_len=18)
        return cls._tool_hint_generic_detail(args)

    @classmethod
    def _tool_hint(cls, tool_calls: list[Any], lang: str | None = None) -> str:
        hint_lang = plan_state.normalize_language(lang)
        parts: list[str] = []
        for tool_call in tool_calls:
            args = getattr(tool_call, "arguments", None)
            if isinstance(args, list):
                args = args[0] if args else None
            safe_args = args if isinstance(args, dict) else {}
            raw_name = str(getattr(tool_call, "name", "") or "")
            name = cls._tool_hint_normalized_name(raw_name)
            label = cls._tool_hint_label(raw_name, hint_lang)
            icon = cls._tool_hint_icon(raw_name)
            short = cls._tool_hint_detail(name, safe_args, hint_lang)
            parts.append(f"{icon} {label}: {short}" if short else f"{icon} {label}")
        return " | ".join(parts)
