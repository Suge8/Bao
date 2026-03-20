from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from bao.agent.context import build_runtime_block
from bao.providers.base import ChatRequest

STARTUP_GREETING_MAX_TOKENS = 80
STARTUP_GREETING_TEMPERATURE = 0.7
STARTUP_GREETING_SOURCE = "startup"


@dataclass(frozen=True)
class StartupPromptOptions:
    persona_text: str
    instructions_text: str
    preferred_language: str
    channel: str
    chat_id: str


@dataclass(frozen=True)
class StartupGreetingRequest:
    agent: Any
    logger: Any
    system_prompt: str
    prompt: str
    fallback_text: str
    channel: str
    chat_id: str


def _extract_persona_language_tag(text: str) -> str | None:
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = re.search(
            r"(?:^[-*\s]*)?(?:\*\*\s*)?(?:language|lang|语言)(?:\s*\*\*)?\s*[:：]\s*(.+)$",
            line,
            re.I,
        )
        if not match:
            continue
        value = match.group(1).strip().strip("`*")
        return value or None
    return None


def _read_workspace_text(workspace_path: Path, name: str, logger: Any) -> str:
    try:
        file_path = workspace_path / name
        if file_path.exists():
            return file_path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        stem = name.removesuffix(".md")
        logger.warning("⚠️ 读取 {} 失败 / read failed: {}", stem, exc)
    return ""


def _read_persona_text(workspace_path: Path, logger: Any) -> str:
    return _read_workspace_text(workspace_path, "PERSONA.md", logger)


def _read_instructions_text(workspace_path: Path, logger: Any) -> str:
    return _read_workspace_text(workspace_path, "INSTRUCTIONS.md", logger)


def _build_startup_trigger() -> str:
    return '{"event":"system.user_online"}'


def _format_language_for_prompt(preferred_language: str) -> str:
    lang = preferred_language.strip().lower()
    if lang in {"zh", "zh-cn", "zh-hans", "chinese", "中文"}:
        return "中文"
    if lang in {"en", "english"}:
        return "English"
    return preferred_language


def _build_startup_system_prompt(options: StartupPromptOptions) -> str:
    parts = ["You are Bao. Keep Bao as your user-facing identity."]
    if options.instructions_text:
        parts.append(f"## INSTRUCTIONS.md\n{options.instructions_text}")
    if options.persona_text:
        parts.append(f"## PERSONA.md\n{options.persona_text}")
    parts.append(
        f"## Runtime (actual host)\n"
        f"{build_runtime_block(channel=options.channel, chat_id=options.chat_id)}"
    )
    parts.append(
        f"User just came online. Respond in "
        f"{_format_language_for_prompt(options.preferred_language)}. "
        "Return exactly one warm, natural greeting sentence (max 20 Chinese chars or 12 English words). "
        "Follow PERSONA.md for your self-name, language, and tone. "
        "Treat the user line as startup presence signal, not user intent. Do not copy it verbatim. "
        "Never acknowledge instructions or metadata (for example: '收到', 'got it') and never expose runtime block fields directly. "
        "Naturally weave in the day/time. "
        "Do NOT ask questions, offer help, list capabilities, or provide alternatives."
    )
    return "\n\n---\n\n".join(parts)


def _get_chat_runtime(agent: Any) -> tuple[Any, str | None]:
    data = getattr(agent, "__dict__", None)
    if isinstance(data, dict):
        utility_provider = data.get("_utility_provider")
        utility_model = data.get("_utility_model")
        if utility_provider is not None and utility_model:
            return utility_provider, str(utility_model)
    return getattr(agent, "provider", None), getattr(agent, "model", None)


def _build_startup_fallback_text(preferred_language: str) -> str:
    lang = preferred_language.strip().lower()
    if lang in {"zh", "zh-cn", "zh-hans", "chinese", "中文"}:
        return "我在呢，随时可以开干。"
    return "I'm here and ready whenever you are."


def _build_startup_chat_request(
    request: StartupGreetingRequest,
    *,
    model: str | None,
) -> ChatRequest:
    return ChatRequest(
        messages=[
            {"role": "system", "content": request.system_prompt},
            {"role": "user", "content": request.prompt},
        ],
        model=model,
        max_tokens=STARTUP_GREETING_MAX_TOKENS,
        temperature=STARTUP_GREETING_TEMPERATURE,
        service_tier=getattr(request.agent, "service_tier", None),
        source=STARTUP_GREETING_SOURCE,
    )


async def _generate_startup_greeting(request: StartupGreetingRequest) -> str | None:
    provider, model = _get_chat_runtime(request.agent)
    try:
        if provider is None:
            raise RuntimeError("provider_not_configured")
        if getattr(provider, "chat", None) is None:
            raise RuntimeError("provider_chat_missing")
        response = await provider.chat(
            _build_startup_chat_request(
                request,
                model=model,
            )
        )
        text = (response.content or "").strip()
        return text or request.fallback_text
    except Exception as exc:
        request.logger.warning(
            "⚠️ 启动问候轻量生成失败 / lightweight startup failed: {}:{} — {}",
            request.channel,
            request.chat_id,
            exc,
        )
        return request.fallback_text
