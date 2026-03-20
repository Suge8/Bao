from __future__ import annotations

from pathlib import Path
from typing import Any

from bao.agent.context import ContextBuilder, ContextBuilderOptions
from bao.bus.events import InboundMessage

ONBOARDING_CONFIRM_HINTS = {
    "zh": "[系统：以上信息已自动保存，无需操作文件。]\n\n",
    "en": "[System: Profile saved automatically. No file operations needed.]\n\n",
}

PERSONA_EXTRACT_SYSTEM = (
    "You extract user profile info from casual text. "
    "Return ONLY valid JSON with these keys: "
    "user_name, user_nickname, bot_name, style, role, interests. "
    "Leave empty string for anything not mentioned."
)


def build_context_builder(
    *,
    workspace: Path,
    prompt_root: Path,
    state_root: Path,
    embedding_config: Any,
    memory_policy: Any,
) -> ContextBuilder:
    return ContextBuilder(
        workspace,
        ContextBuilderOptions(
            prompt_root=prompt_root,
            state_root=state_root,
            embedding_config=embedding_config,
            memory_policy=memory_policy,
        ),
    )


def build_persona_extract_prompt(content: str) -> str:
    return (
        f"User's reply to onboarding questions:\n\n{content}\n\n"
        'Return JSON like: {"user_name": "...", "user_nickname": "...", '
        '"bot_name": "...", "style": "...", "role": "", "interests": ""}'
    )


def build_onboarding_confirmation_message(msg: InboundMessage, *, lang: str) -> InboundMessage:
    confirm_hint = ONBOARDING_CONFIRM_HINTS[lang]
    return InboundMessage(
        channel=msg.channel,
        sender_id=msg.sender_id,
        chat_id=msg.chat_id,
        content=f"{confirm_hint}{msg.content}",
        media=msg.media,
        metadata=msg.metadata,
    )
