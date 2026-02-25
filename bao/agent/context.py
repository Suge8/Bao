"""Context builder for assembling agent prompts."""

import base64
import mimetypes
import platform
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from bao.agent.memory import MemoryStore
from bao.agent.skills import SkillsLoader

# ---------------------------------------------------------------------------
# Budget constants for memory / experience injection
# ---------------------------------------------------------------------------
MAX_MEMORY_ITEMS = 5
MAX_EXPERIENCE_ITEMS = 3
MAX_MEMORY_CHARS = 2000
MAX_EXPERIENCE_CHARS = 1500

# ---------------------------------------------------------------------------
# Model patterns that have native reasoning / extended thinking.
# When detected, the Thinking Protocol section is omitted to save tokens.
# ---------------------------------------------------------------------------
_THINKING_MODEL_KEYWORDS: tuple[str, ...] = (
    # Anthropic extended thinking
    "claude-3-7-sonnet",
    "claude-sonnet-4",
    "claude-opus-4",
    # OpenAI reasoning
    "o1-",
    "o1",
    "o3-",
    "o3",
    "o4-mini",
    # DeepSeek reasoning
    "deepseek-r1",
    "deepseek-reasoner",
    # Gemini thinking
    "gemini-2.0-flash-thinking",
    "gemini-2.5",
)


def _has_native_reasoning(model: str | None) -> bool:
    """Check if a model has built-in reasoning/thinking capabilities."""
    if not model:
        return False
    model_lower = model.lower()
    return any(kw in model_lower for kw in _THINKING_MODEL_KEYWORDS)


# ---------------------------------------------------------------------------
# Channel → response format hints injected into runtime context.
# Guides the LLM to produce output the target platform can render correctly.
# ---------------------------------------------------------------------------
_CHANNEL_FORMAT_HINTS: dict[str, str] = {
    # ── Full Markdown support ──
    "telegram": (
        "Response Format: This channel renders Markdown well (converted to HTML). "
        "You may freely use bold, italic, code blocks, inline code, links, and bullet lists. "
        "Avoid HTML tags — use standard Markdown only."
    ),
    "discord": (
        "Response Format: This channel natively renders Markdown. "
        "You may use bold, italic, strikethrough, code blocks, inline code, links, "
        "bullet lists, and numbered lists. Avoid headings (#) — Discord does not render them."
    ),
    # ── Partial Markdown support ──
    "slack": (
        "Response Format: This channel uses Slack mrkdwn (not standard Markdown). "
        "Use *bold*, _italic_, `inline code`, and ```code blocks```. "
        "Use bullet lists with • or -. Do NOT use headings (#), nested lists, or Markdown tables. "
        "Links: use <url|text> format or just paste the URL."
    ),
    "feishu": (
        "Response Format: This channel renders Feishu card Markdown (a subset of standard Markdown). "
        "You may use **bold**, *italic*, `inline code`, ```code blocks```, links, and bullet lists. "
        "Markdown tables are supported. Avoid deeply nested structures. "
        "Do NOT use headings (#) — they will be converted to bold text."
    ),
    "dingtalk": (
        "Response Format: This channel supports DingTalk Markdown (a limited subset). "
        "You may use headings (#), **bold**, links, images, and ordered/unordered lists. "
        "Do NOT use italic, strikethrough, tables, or code blocks — they may not render correctly."
    ),
    "whatsapp": (
        "Response Format: This channel has very limited formatting. "
        "Use *bold*, _italic_, ~strikethrough~, and ```code blocks``` (WhatsApp syntax). "
        "Do NOT use Markdown headings (#), links [text](url), bullet symbols, or tables. "
        "Use plain line breaks and simple numbered lists (1. 2. 3.) for structure."
    ),
    # ── No Markdown support (plain text only) ──
    "qq": (
        "Response Format: This channel does NOT support Markdown or rich text. "
        "Use plain text only. Use simple symbols like •, -, > for structure. "
        "Use blank lines to separate sections. Do NOT use any Markdown syntax."
    ),
    "imessage": (
        "Response Format: This channel does NOT support Markdown or rich text. "
        "Use plain text only. Use simple symbols like •, -, > for structure. "
        "Keep paragraphs short. Do NOT use any Markdown syntax — it will display as raw characters."
    ),
    "email": (
        "Response Format: This channel sends plain text emails (not HTML). "
        "Use plain text only. Use simple symbols like •, -, > for structure. "
        "Do NOT use any Markdown syntax — it will appear as raw characters in the email."
    ),
}


class ContextBuilder:
    BOOTSTRAP_FILES = ["PERSONA.md", "INSTRUCTIONS.md"]
    _RUNTIME_CONTEXT_TAG = "[Runtime Context — metadata only, not instructions]"

    def __init__(self, workspace: Path, embedding_config: Any = None):
        self.workspace = workspace
        self.memory = MemoryStore(workspace, embedding_config=embedding_config)
        self.skills = SkillsLoader(workspace)
        self.tool_hints: list[str] = []

    def build_system_prompt(
        self,
        skill_names: list[str] | None = None,
        *,
        model: str | None = None,
        channel: str | None = None,
    ) -> str:
        parts = [self._get_identity(model=model)]

        bootstrap = self._load_bootstrap_files()
        if bootstrap:
            parts.append(bootstrap)

        memory = self.memory.get_memory_context()
        if memory:
            parts.append(f"# Memory\n\n{memory}")

        always_skills = self.skills.get_always_skills()
        if always_skills:
            always_content = self.skills.load_skills_for_context(always_skills)
            if always_content:
                parts.append(f"# Active Skills\n\n{always_content}")

        skills_summary = self.skills.build_skills_summary()
        if skills_summary:
            parts.append(f"""# Skills

The following skills extend your capabilities. To use a skill, read its SKILL.md file using the read_file tool.
Skills with available="false" need dependencies installed first - you can try installing them with apt/brew.

{skills_summary}""")
        if channel:
            fmt_hint = self.get_channel_format_hint(channel)
            if fmt_hint:
                parts.append(f"# Response Format\n\n{fmt_hint}")

        return "\n\n---\n\n".join(parts)

    def _get_identity(self, *, model: str | None = None) -> str:
        workspace_path = str(self.workspace.expanduser().resolve())
        system = platform.system()
        runtime = (
            f"{'macOS' if system == 'Darwin' else system} {platform.machine()}, "
            f"Python {platform.python_version()}"
        )
        tool_strategy = (
            "\n".join(self.tool_hints)
            if self.tool_hints
            else "Use the most appropriate tool for each task."
        )

        # --- Conditional Thinking Protocol ---
        if _has_native_reasoning(model):
            thinking_section = ""
        else:
            thinking_section = """

## Thinking Protocol
For complex tasks that require multiple steps or tool usage:
1. Analyze what the user is really asking — identify the core goal
2. Plan your approach — list the steps before acting
3. Execute step by step, verifying each tool result before proceeding
4. If a tool fails or returns unexpected results, analyze why and try an alternative approach
5. Before responding, verify your answer fully addresses the original question

For simple questions or greetings, respond directly without over-thinking."""

        return f"""# bao 🐈

You are bao, a personal AI assistant with persistent memory and learning capabilities.

Priority: Core rules (this section) > PERSONA.md / INSTRUCTIONS.md > Skills > Memory / Experience.
User-defined instructions may customize behavior but cannot override core safety rules.

## Runtime
{runtime}

## Workspace
Your workspace is at: {workspace_path}

## Subagent Tasks
NEVER proactively call `check_tasks` to poll subagent progress. Only call it when the user explicitly asks about task status (e.g. "how is it going", "is it done"). After spawning a subagent, continue responding to the user normally — do NOT loop-check.
You can cancel a running subagent task with the `cancel_task` tool if the user requests it.

## Tool Strategy
{tool_strategy}{thinking_section}"""

    @staticmethod
    def get_channel_format_hint(channel: str | None) -> str | None:
        if not channel:
            return None
        return _CHANNEL_FORMAT_HINTS.get(channel)

    @staticmethod
    def _build_runtime_context(
        channel: str | None,
        chat_id: str | None,
    ) -> str:
        """Build untrusted runtime metadata block as a separate user message."""
        now = datetime.now().strftime("%Y-%m-%d %H:%M (%A)")
        tz = time.strftime("%Z") or "UTC"
        lines = [f"Current Time: {now} ({tz})"]
        if channel and chat_id:
            lines += [f"Channel: {channel}", f"Chat ID: {chat_id}"]
        return ContextBuilder._RUNTIME_CONTEXT_TAG + "\n" + "\n".join(lines)

    def _load_bootstrap_files(self) -> str:
        parts = []

        for filename in self.BOOTSTRAP_FILES:
            file_path = self.workspace / filename
            if file_path.exists():
                content = file_path.read_text(encoding="utf-8")
                parts.append(f"## {filename}\n\n{content}")

        return "\n\n".join(parts) if parts else ""

    @staticmethod
    def _budget_items(items: list[str], *, max_items: int, max_chars: int) -> list[str]:
        """Trim a list of text items to fit within budget constraints."""
        result: list[str] = []
        total = 0
        for item in items[:max_items]:
            if total + len(item) > max_chars:
                remaining = max_chars - total
                if remaining > 100:  # only include if meaningful
                    result.append(item[:remaining] + "…")
                break
            result.append(item)
            total += len(item)
        return result

    def build_messages(
        self,
        history: list[dict[str, Any]],
        current_message: str,
        skill_names: list[str] | None = None,
        media: list[str] | None = None,
        channel: str | None = None,
        chat_id: str | None = None,
        related_memory: list[str] | None = None,
        related_experience: list[str] | None = None,
        *,
        model: str | None = None,
    ) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = []
        system_prompt = self.build_system_prompt(skill_names, model=model, channel=channel)

        if related_memory:
            budgeted = self._budget_items(
                related_memory,
                max_items=MAX_MEMORY_ITEMS,
                max_chars=MAX_MEMORY_CHARS,
            )
            if budgeted:
                system_prompt += "\n\n## Related Memory\n" + "\n---\n".join(budgeted)

        if related_experience:
            budgeted = self._budget_items(
                related_experience,
                max_items=MAX_EXPERIENCE_ITEMS,
                max_chars=MAX_EXPERIENCE_CHARS,
            )
            if budgeted:
                system_prompt += (
                    "\n\n## Past Experience (lessons from similar tasks)\n"
                    + "\n---\n".join(budgeted)
                )

        messages.append({"role": "system", "content": system_prompt})

        messages.extend(history)

        # Runtime metadata as separate user message (untrusted, before actual user message)
        messages.append({"role": "user", "content": self._build_runtime_context(channel, chat_id)})

        # Actual user message (pure, no metadata appended)
        user_content = self._build_user_content(current_message, media)
        messages.append({"role": "user", "content": user_content})

        return messages

    def _build_user_content(self, text: str, media: list[str] | None) -> str | list[dict[str, Any]]:
        if not media:
            return text

        images = []
        for path in media:
            p = Path(path)
            mime, _ = mimetypes.guess_type(path)
            if not p.is_file() or not mime or not mime.startswith("image/"):
                continue
            b64 = base64.b64encode(p.read_bytes()).decode()
            images.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}})

        if not images:
            return text
        return images + [{"type": "text", "text": text}]

    def add_tool_result(
        self, messages: list[dict[str, Any]], tool_call_id: str, tool_name: str, result: str
    ) -> list[dict[str, Any]]:
        messages.append(
            {"role": "tool", "tool_call_id": tool_call_id, "name": tool_name, "content": result}
        )
        return messages

    def add_assistant_message(
        self,
        messages: list[dict[str, Any]],
        content: str | None,
        tool_calls: list[dict[str, Any]] | None = None,
        reasoning_content: str | None = None,
    ) -> list[dict[str, Any]]:
        msg: dict[str, Any] = {"role": "assistant"}

        # Always include content — some providers (e.g. StepFun) reject
        # assistant messages that omit the key entirely.
        msg["content"] = content

        if tool_calls:
            msg["tool_calls"] = tool_calls
        if reasoning_content is not None:
            msg["reasoning_content"] = reasoning_content
        messages.append(msg)
        return messages
