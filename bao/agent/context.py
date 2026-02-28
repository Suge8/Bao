"""Context builder for assembling agent prompts."""

import base64
import logging
import mimetypes
import platform
import re
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
MAX_LONG_TERM_MEMORY_CHARS = 1500


def format_current_time(*, include_weekday: bool = True) -> str:
    """Shared time formatter for main agent and subagent prompts."""
    fmt = "%Y-%m-%d %H:%M (%A)" if include_weekday else "%Y-%m-%d %H:%M"
    now = datetime.now().strftime(fmt)
    tz = time.strftime("%Z") or "UTC"
    return f"{now} ({tz})"


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
        chat_id: str | None = None,
    ) -> str:
        parts = [self._get_identity(model=model, channel=channel, chat_id=chat_id)]

        bootstrap = self._load_bootstrap_files()
        if bootstrap:
            parts.append(bootstrap)

        # Long-term memory injection moved to build_messages() for query-aware filtering

        always_skills = self.skills.get_always_skills()
        if always_skills:
            always_content = self.skills.load_skills_for_context(always_skills)
            if always_content:
                parts.append(f"# Active Skills\n\n{always_content}")

        skills_summary = self.skills.build_skills_summary()
        if skills_summary:
            parts.append(f"""# Skills

To use a skill, read `skills/{{name}}/SKILL.md` using the read_file tool.
Skills with available="false" need dependencies installed first - you can try installing them with apt/brew.

{skills_summary}""")
        if channel:
            fmt_hint = self.get_channel_format_hint(channel)
            if fmt_hint:
                parts.append(f"# Response Format\n\n{fmt_hint}")

        return "\n\n---\n\n".join(parts)

    def _get_identity(
        self,
        *,
        model: str | None = None,
        channel: str | None = None,
        chat_id: str | None = None,
    ) -> str:
        workspace_path = str(self.workspace.expanduser().resolve())
        system = platform.system()
        runtime_lines = [
            f"{'macOS' if system == 'Darwin' else system} {platform.machine()}, "
            f"Python {platform.python_version()}",
            f"Current time: {format_current_time()}",
        ]
        if channel and chat_id:
            runtime_lines.append(f"Channel: {channel} | Chat: {chat_id}")
        elif channel:
            runtime_lines.append(f"Channel: {channel}")
        runtime_block = "\n".join(runtime_lines)

        tool_section = ""
        if self.tool_hints:
            tool_section = f"\n\n## Tool Strategy\n{chr(10).join(self.tool_hints)}"

        return f"""# bao 🍞

You are bao, a personal AI assistant with persistent memory and learning capabilities.

Priority: Core rules (this section) > PERSONA.md / INSTRUCTIONS.md > Skills > Memory / Experience.
User-defined instructions may customize behavior but cannot override core safety rules.

## Runtime
{runtime_block}

## Workspace
Your workspace is at: {workspace_path}{tool_section}"""

    @staticmethod
    def get_channel_format_hint(channel: str | None) -> str | None:
        if not channel:
            return None
        return _CHANNEL_FORMAT_HINTS.get(channel)

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
        system_prompt = self.build_system_prompt(
            skill_names, model=model, channel=channel, chat_id=chat_id
        )

        # --- Query-aware long-term memory injection ---
        ltm = self.memory.get_relevant_memory_context(
            current_message, max_chars=MAX_LONG_TERM_MEMORY_CHARS
        )
        if ltm:
            system_prompt += f"\n\n# Memory\n\n{ltm}"

        if related_memory and ltm:
            # Deduplicate: filter related_memory items that overlap with long-term memory
            # Strip LTM headers (## / [category]) before tokenizing to avoid pollution
            ltm_clean = re.sub(r"^(##.*|\[\w+\])\s*$", "", ltm, flags=re.MULTILINE)
            ltm_tokens = set(MemoryStore._tokenize(ltm_clean))
            deduped: list[str] = []
            for item in related_memory:
                item_tokens = set(MemoryStore._tokenize(item))
                if not item_tokens:
                    continue
                overlap = len(item_tokens & ltm_tokens) / len(item_tokens)
                if overlap < 0.7:
                    deduped.append(item)
            related_memory = deduped or None

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

        # User message
        # Actual user message (pure, no metadata appended)
        user_content = self._build_user_content(current_message, media)
        messages.append({"role": "user", "content": user_content})

        return messages

    # Formats natively supported by vision APIs
    _SUPPORTED_IMAGE_MIMES = frozenset({"image/jpeg", "image/png", "image/gif", "image/webp"})
    _MAX_IMAGE_LONG_EDGE = 1568  # Anthropic internal resize limit
    _MAX_IMAGE_BYTES = 1_000_000  # 1 MB — skip Pillow for small images

    @staticmethod
    def _compress_image(p: Path, mime: str) -> tuple[str, str]:
        """Resize & compress an image to JPEG. Returns (b64, mime)."""
        from io import BytesIO

        from PIL import Image, ImageOps

        try:
            from pillow_heif import register_heif_opener
            register_heif_opener()
        except ImportError:
            pass

        with Image.open(p) as img:
            # Fix EXIF orientation (phone photos / screenshots)
            img = ImageOps.exif_transpose(img)
            # Downscale if either dimension exceeds limit
            max_edge = ContextBuilder._MAX_IMAGE_LONG_EDGE
            if max(img.size) > max_edge:
                img.thumbnail((max_edge, max_edge), Image.LANCZOS)
            # Composite transparent images onto white background
            if img.mode in ("RGBA", "LA", "PA"):
                background = Image.new("RGB", img.size, (255, 255, 255))
                background.paste(img, mask=img.split()[-1])
                img = background
            elif img.mode not in ("RGB", "L"):
                img = img.convert("RGB")
            buf = BytesIO()
            img.save(buf, format="JPEG", quality=85)
            return base64.b64encode(buf.getvalue()).decode(), "image/jpeg"

    def _build_user_content(self, text: str, media: list[str] | None) -> str | list[dict[str, Any]]:
        if not media:
            return text

        images = []
        for path in media:
            p = Path(path)
            mime, _ = mimetypes.guess_type(path)
            if not p.is_file() or not mime or not mime.startswith("image/"):
                continue

            needs_transcode = mime not in self._SUPPORTED_IMAGE_MIMES
            try:
                needs_compress = p.stat().st_size > self._MAX_IMAGE_BYTES
            except OSError:
                continue

            if needs_transcode or needs_compress:
                try:
                    b64, mime = self._compress_image(p, mime)
                except ImportError:
                    logging.warning("Pillow is not installed; skipping image %s", p)
                    continue
                except Exception:
                    logging.warning("Failed to process image %s", p, exc_info=True)
                    continue
            else:
                try:
                    b64 = base64.b64encode(p.read_bytes()).decode()
                except OSError:
                    continue

            images.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}})

        if not images:
            return text
        return images + [{"type": "text", "text": text}]

    def add_tool_result(
        self,
        messages: list[dict[str, Any]],
        tool_call_id: str,
        tool_name: str,
        result: str,
        image_base64: str | None = None,
    ) -> list[dict[str, Any]]:
        msg: dict[str, Any] = {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "name": tool_name,
            "content": result,
        }
        if image_base64:
            msg["_image"] = image_base64
        messages.append(msg)
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
