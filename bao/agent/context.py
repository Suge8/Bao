"""Context builder for assembling agent prompts."""

import base64
import mimetypes
import platform
import time as _time
from datetime import datetime
from pathlib import Path
from typing import Any

from bao.agent.memory import MemoryStore
from bao.agent.skills import SkillsLoader


class ContextBuilder:
    BOOTSTRAP_FILES = ["PERSONA.md", "INSTRUCTIONS.md"]

    def __init__(self, workspace: Path, embedding_config: Any = None):
        self.workspace = workspace
        self.memory = MemoryStore(workspace, embedding_config=embedding_config)
        self.skills = SkillsLoader(workspace)
        self.tool_hints: list[str] = []

    def build_system_prompt(self, skill_names: list[str] | None = None) -> str:
        parts = [self._get_identity()]

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

        return "\n\n---\n\n".join(parts)

    def _get_identity(self) -> str:
        now = datetime.now().strftime("%Y-%m-%d %H:%M (%A)")
        tz = _time.strftime("%Z") or "UTC"
        workspace_path = str(self.workspace.expanduser().resolve())
        system = platform.system()
        runtime = f"{'macOS' if system == 'Darwin' else system} {platform.machine()}, Python {platform.python_version()}"
        tool_strategy = (
            "\n".join(self.tool_hints)
            if self.tool_hints
            else "Use the most appropriate tool for each task."
        )

        return f"""# bao 🐈

You are bao, a helpful AI assistant. You have access to tools that allow you to:
- Read, write, and edit files
- Execute shell commands
- Fetch and read web pages
- Send messages to users on chat channels
- Spawn subagents for complex background tasks

## Current Time
{now} ({tz})

## Runtime
{runtime}

## Workspace
Your workspace is at: {workspace_path}

IMPORTANT: When responding to direct questions or conversations, reply directly with your text response.
Only use the 'message' tool when you need to send a message to a specific chat channel (like WhatsApp).
For normal conversation, just respond with text - do not call the message tool.

Always be helpful, accurate, and concise. Before calling tools, briefly tell the user what you're about to do (one short sentence in the user's language).

## Tool Strategy
{tool_strategy}

## Thinking Protocol
For complex tasks that require multiple steps or tool usage:
1. Analyze what the user is really asking — identify the core goal
2. Plan your approach — list the steps before acting
3. Execute step by step, verifying each tool result before proceeding
4. If a tool fails or returns unexpected results, analyze why and try an alternative approach
5. Before responding, verify your answer fully addresses the original question

For simple questions or greetings, respond directly without over-thinking."""

    def _load_bootstrap_files(self) -> str:
        parts = []

        for filename in self.BOOTSTRAP_FILES:
            file_path = self.workspace / filename
            if file_path.exists():
                content = file_path.read_text(encoding="utf-8")
                parts.append(f"## {filename}\n\n{content}")

        return "\n\n".join(parts) if parts else ""

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
    ) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = []
        system_prompt = self.build_system_prompt(skill_names)

        if related_memory:
            system_prompt += "\n\n## Related Memory\n" + "\n---\n".join(related_memory)

        if related_experience:
            system_prompt += (
                "\n\n## Past Experience (lessons from similar tasks)\n"
                + "\n---\n".join(related_experience)
            )

        if channel and chat_id:
            system_prompt += f"\n\n## Current Session\nChannel: {channel}\nChat ID: {chat_id}"
        messages.append({"role": "system", "content": system_prompt})

        messages.extend(history)

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
