"""Anthropic Provider — native SDK with Extended Thinking and Prompt Caching support."""

from __future__ import annotations

import asyncio
import json
from typing import Any, Awaitable, Callable

import anthropic
from loguru import logger

from bao.providers.base import LLMProvider, LLMResponse, ToolCallRequest
from bao.providers.retry import (
    DEFAULT_BASE_DELAY,
    DEFAULT_MAX_RETRIES,
    ProgressCallbackError,
    StreamInterruptedError,
    compute_retry_delay,
    emit_progress,
    emit_progress_reset,
    safe_error_text,
    should_retry_exception,
)

_MAX_RETRIES = DEFAULT_MAX_RETRIES
_BASE_DELAY = DEFAULT_BASE_DELAY


class AnthropicProvider(LLMProvider):
    """
    Anthropic Claude provider using the official SDK.

    Supports:
    - Claude 3.5 Sonnet, 3.7 Sonnet, 3.7 Haiku
    - Adaptive Thinking (Claude models with thinking support)
    - Prompt Caching (cache_control on system messages and tools)
    - Native tool use (tool_use content blocks)

    Models: claude-3-5-sonnet-20241022, claude-3-7-sonnet-20250514, claude-3-7-haiku-20250514, etc.
    """

    # Models that support extended thinking
    EXTENDED_THINKING_MODELS = frozenset(
        {
            "claude-3-7-sonnet-20250514",
            "claude-sonnet-4-20250514",
        }
    )

    def __init__(
        self,
        api_key: str | None = None,
        default_model: str = "claude-sonnet-4-20250514",
        base_url: str | None = None,
    ):
        super().__init__(api_key, None)
        self.default_model = default_model
        client_kwargs: dict[str, Any] = {"api_key": api_key, "max_retries": 0}
        if base_url:
            client_kwargs["base_url"] = base_url
            # Some proxies block SDK-identifying headers → override them.
            client_kwargs["default_headers"] = {
                "User-Agent": "curl/8.7.1",
                "X-Stainless-Lang": "",
                "X-Stainless-Package-Version": "",
                "X-Stainless-OS": "",
                "X-Stainless-Arch": "",
                "X-Stainless-Runtime": "",
                "X-Stainless-Runtime-Version": "",
                "X-Stainless-Async": "",
            }
        self._client = anthropic.AsyncAnthropic(**client_kwargs)

    def _resolve_model(self, model: str) -> str:
        """Strip provider prefix (e.g. 'anthropic/', 'custom/') if present."""
        if "/" in model:
            return model.split("/", 1)[1]
        return model

    def _supports_extended_thinking(self, model: str) -> bool:
        """Check if model supports extended thinking."""
        model_lower = model.lower()
        return any(think_model in model_lower for think_model in self.EXTENDED_THINKING_MODELS)

    @staticmethod
    def _budget_from_reasoning_effort(reasoning_effort: str | None) -> int | None:
        if not reasoning_effort:
            return None
        effort = reasoning_effort.strip().lower()
        return {"low": 2048, "medium": 4096, "high": 8192}.get(effort)

    def _convert_messages(
        self,
        messages: list[dict[str, Any]],
    ) -> tuple[str | None, list[dict[str, Any]]]:
        """Convert OpenAI-style messages to Anthropic format.

        Returns: (system_prompt, anthropic_messages)
        """
        system_prompt: str | None = None
        anthropic_messages: list[dict[str, Any]] = []

        for msg in messages:
            role = msg.get("role")
            content = msg.get("content")

            if role == "system":
                # Anthropic uses system as a separate parameter
                if isinstance(content, str):
                    system_prompt = content
                else:
                    # Convert content blocks
                    system_prompt = self._convert_content_blocks(content)
            elif role == "user":
                anthropic_messages.append(
                    {
                        "role": "user",
                        "content": self._convert_user_content(content),
                    }
                )
            elif role == "assistant":
                # Assistant message may have content and/or tool calls
                parts = []
                if content:
                    parts.append({"type": "text", "text": content})

                # Handle tool calls
                for tc in msg.get("tool_calls", []) or []:
                    fn = tc.get("function") or {}
                    fn_args = fn.get("arguments", {})
                    if isinstance(fn_args, str):
                        try:
                            parsed = json.loads(fn_args)
                            fn_args = parsed if isinstance(parsed, dict) else {}
                        except json.JSONDecodeError:
                            fn_args = {}
                    elif not isinstance(fn_args, dict):
                        fn_args = {}
                    parts.append(
                        {
                            "type": "tool_use",
                            "id": tc.get("id", f"tool_{tc.get('name', 'unknown')}"),
                            "name": fn.get("name", ""),
                            "input": fn_args,
                        }
                    )

                if parts:
                    anthropic_messages.append({"role": "assistant", "content": parts})
            elif role == "tool":
                # Tool result (with optional screenshot image)
                tool_content = content if isinstance(content, str) else str(content)
                tool_result_content: Any = tool_content
                img_b64 = msg.get("_image")
                if img_b64:
                    tool_result_content = [
                        {"type": "text", "text": tool_content},
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/jpeg",
                                "data": img_b64,
                            },
                        },
                    ]
                anthropic_messages.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": msg.get("tool_call_id", "unknown"),
                                "content": tool_result_content,
                            }
                        ],
                    }
                )

        return system_prompt, anthropic_messages

    def _convert_user_content(self, content: Any) -> str | list[dict[str, Any]]:
        """Convert user message content to Anthropic format."""
        if isinstance(content, str):
            return content

        if isinstance(content, list):
            parts = []
            for item in content:
                if not isinstance(item, dict):
                    continue
                item_type = item.get("type")
                if item_type == "text":
                    parts.append({"type": "text", "text": item.get("text", "")})
                elif item_type == "image_url":
                    # Handle image URLs
                    url_data = item.get("image_url") or {}
                    url = url_data.get("url", "")
                    # Anthropic expects base64 or media type
                    if url.startswith("data:"):
                        header, _, b64_data = url.partition(",")
                        media_type = "image/jpeg"
                        if header.startswith("data:") and ";" in header:
                            media_type = header[len("data:") : header.index(";")]
                        if not b64_data:
                            continue
                        parts.append(
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": media_type,
                                    "data": b64_data,
                                },
                            }
                        )
                    else:
                        # For URLs, we'd need to fetch - for now, skip
                        pass
            return parts if parts else ""

        return str(content)

    def _convert_content_blocks(self, content: Any) -> str:
        """Convert content blocks to string for system prompt."""
        if isinstance(content, str):
            return content

        if isinstance(content, list):
            texts = []
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "text":
                        texts.append(block.get("text", ""))
            return "\n".join(texts)

        return str(content)

    def _convert_tools(self, tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Convert OpenAI function-calling tools to Anthropic tool format."""
        anthropic_tools = []

        for tool in tools:
            fn = (tool.get("function") or {}) if tool.get("type") == "function" else tool
            name = fn.get("name")
            if not name:
                continue

            description = fn.get("description", "")
            parameters = fn.get("parameters") or {}

            anthropic_tools.append(
                {
                    "name": name,
                    "description": description,
                    "input_schema": parameters if isinstance(parameters, dict) else {},
                }
            )

        return anthropic_tools

    def _apply_cache_control(
        self,
        system_prompt: str | None,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
    ) -> tuple[
        str | list[dict[str, Any]] | None, list[dict[str, Any]], list[dict[str, Any]] | None
    ]:
        """Apply cache_control for prompt caching support."""
        new_system = system_prompt
        if system_prompt:
            new_system = [
                {"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}
            ]

        new_messages = []
        for msg in messages:
            # Add cache_control to last message if it's from user
            if msg.get("role") == "user":
                content = msg.get("content")
                if isinstance(content, str):
                    new_content = [
                        {"type": "text", "text": content, "cache_control": {"type": "ephemeral"}}
                    ]
                elif isinstance(content, list):
                    new_content = list(content)
                    if new_content:
                        new_content[-1] = {
                            **new_content[-1],
                            "cache_control": {"type": "ephemeral"},
                        }
                else:
                    new_content = content
                new_messages.append({**msg, "content": new_content})
            else:
                new_messages.append(msg)

        new_tools = None
        if tools:
            new_tools = list(tools)
            new_tools[-1] = {**new_tools[-1], "cache_control": {"type": "ephemeral"}}

        return new_system, new_messages, new_tools

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        on_progress: Callable[[str], Awaitable[None]] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """
        Send a chat completion request via Anthropic API.

        Args:
            messages: List of message dicts with 'role' and 'content'.
            tools: Optional list of tool definitions in OpenAI format.
            model: Model identifier (e.g., 'claude-sonnet-4-20250514').
            max_tokens: Maximum tokens in response.
            temperature: Sampling temperature.

        Returns:
            LLMResponse with content and/or tool calls.
        """
        original_model = model or self.default_model
        resolved_model = self._resolve_model(original_model)

        # Convert messages
        system_prompt, anthropic_messages = self._convert_messages(messages)

        # Prepare request
        request_kwargs: dict[str, Any] = {
            "model": resolved_model,
            "max_tokens": max(1, max_tokens),
            "temperature": temperature,
        }

        # Add system prompt
        if system_prompt:
            request_kwargs["system"] = system_prompt

        # Add messages
        request_kwargs["messages"] = anthropic_messages

        # Add tools
        if tools:
            request_kwargs["tools"] = self._convert_tools(tools)

        # Handle thinking (adaptive thinking for supported Claude models)
        thinking = kwargs.get("thinking")
        if thinking is None:
            effort_budget = self._budget_from_reasoning_effort(kwargs.get("reasoning_effort"))
            if effort_budget:
                thinking = {"type": "adaptive", "budget_tokens": effort_budget}
        if thinking is None and self._supports_extended_thinking(resolved_model):
            # Default to adaptive thinking for supported models
            thinking = {"type": "adaptive", "budget_tokens": 1024}

        if thinking:
            request_kwargs["thinking"] = thinking

        last_err: Exception | None = None
        content = ""
        for attempt in range(_MAX_RETRIES + 1):
            try:
                content = ""
                tool_calls: list[ToolCallRequest] = []
                reasoning_content: str | None = None
                thinking_blocks: list[dict[str, Any]] = []
                current_tool_id: str | None = None
                current_tool_name: str | None = None
                partial_json = ""

                async with self._client.messages.stream(**request_kwargs) as stream:
                    async for event in stream:
                        if event.type == "content_block_start":
                            if hasattr(event.content_block, "type"):
                                if event.content_block.type == "tool_use":
                                    current_tool_id = event.content_block.id
                                    current_tool_name = event.content_block.name
                                    partial_json = ""
                        elif event.type == "content_block_delta":
                            delta = event.delta
                            if delta.type == "text_delta":
                                content += delta.text
                                await emit_progress(on_progress, delta.text)
                            elif delta.type == "input_json_delta":
                                partial_json += delta.partial_json
                            elif delta.type == "thinking_delta":
                                if reasoning_content is None:
                                    reasoning_content = ""
                                reasoning_content += delta.thinking
                        elif event.type == "content_block_stop":
                            if current_tool_id and current_tool_name:
                                try:
                                    args = json.loads(partial_json) if partial_json else {}
                                except json.JSONDecodeError as exc:
                                    raise RuntimeError("incomplete tool json in stream") from exc
                                tool_calls.append(
                                    ToolCallRequest(
                                        id=current_tool_id,
                                        name=current_tool_name,
                                        arguments=args,
                                    )
                                )
                                current_tool_id = None
                                current_tool_name = None
                                partial_json = ""

                    final_msg = await stream.get_final_message()
                    for block in getattr(final_msg, "content", []) or []:
                        if getattr(block, "type", None) == "thinking":
                            thinking_blocks.append(
                                {
                                    "type": "thinking",
                                    "thinking": str(getattr(block, "thinking", "") or ""),
                                }
                            )

                # Usage from final message
                usage = {
                    "prompt_tokens": final_msg.usage.input_tokens,
                    "completion_tokens": final_msg.usage.output_tokens,
                    "total_tokens": final_msg.usage.input_tokens + final_msg.usage.output_tokens,
                }

                # Map finish reason
                stop = final_msg.stop_reason
                if stop == "end_turn":
                    finish_reason = "stop"
                elif stop == "max_tokens":
                    finish_reason = "length"
                elif stop == "tool_use":
                    finish_reason = "tool_calls"
                else:
                    finish_reason = stop or "stop"

                return LLMResponse(
                    content=content or None,
                    tool_calls=tool_calls,
                    finish_reason=finish_reason,
                    usage=usage,
                    reasoning_content=reasoning_content,
                    thinking_blocks=thinking_blocks or None,
                )
            except asyncio.CancelledError:
                raise
            except ProgressCallbackError as exc:
                if isinstance(exc, StreamInterruptedError):
                    return LLMResponse(content=content or None, finish_reason="interrupted")
                cause = exc.__cause__ or exc
                return LLMResponse(
                    content=f"Error calling Anthropic progress callback: {safe_error_text(cause)}",
                    finish_reason="error",
                )
            except Exception as e:
                last_err = e
                is_retryable = should_retry_exception(e)

                if is_retryable and attempt < _MAX_RETRIES:
                    try:
                        await emit_progress_reset(on_progress)
                    except ProgressCallbackError as exc:
                        if isinstance(exc, StreamInterruptedError):
                            return LLMResponse(content=content or None, finish_reason="interrupted")
                        cause = exc.__cause__ or exc
                        return LLMResponse(
                            content=(
                                f"Error calling Anthropic progress callback: "
                                f"{safe_error_text(cause)}"
                            ),
                            finish_reason="error",
                        )

                    delay = compute_retry_delay(e, attempt, base_delay=_BASE_DELAY)
                    logger.warning(
                        "⚠️ Anthropic 重试中 / retrying: transient error (attempt {}/{}), in {:.1f}s: {}",
                        attempt + 1,
                        _MAX_RETRIES + 1,
                        delay,
                        safe_error_text(e),
                    )
                    await asyncio.sleep(delay)
                    continue

                # Non-retryable or retries exhausted
                if attempt > 0:
                    logger.error(
                        "❌ Anthropic 最终失败 / final failure: after {} attempts: {}",
                        attempt + 1,
                        safe_error_text(e),
                    )
                return LLMResponse(
                    content=f"Error calling Anthropic: {safe_error_text(e)}",
                    finish_reason="error",
                )

        # Should not reach here, but safety net
        return LLMResponse(
            content=f"Error calling Anthropic: {safe_error_text(last_err or RuntimeError('unknown error'))}",
            finish_reason="error",
        )

    def _parse_response(self, response: Any) -> LLMResponse:
        """Parse Anthropic response into LLMResponse."""
        content = ""
        tool_calls: list[ToolCallRequest] = []
        reasoning_content: str | None = None
        thinking_blocks: list[dict[str, Any]] = []
        finish_reason = "stop"

        for block in response.content:
            if block.type == "text":
                content += block.text
            elif block.type == "tool_use":
                tool_calls.append(
                    ToolCallRequest(
                        id=block.id,
                        name=block.name,
                        arguments=block.input,
                    )
                )
            elif block.type == "thinking":
                reasoning_content = block.thinking
                thinking_blocks.append({"type": "thinking", "thinking": block.thinking})

        # Map finish reason
        if response.stop_reason == "end_turn":
            finish_reason = "stop"
        elif response.stop_reason == "max_tokens":
            finish_reason = "length"
        elif response.stop_reason == "tool_use":
            finish_reason = "tool_calls"
        else:
            finish_reason = response.stop_reason or "stop"

        # Usage
        usage = {
            "prompt_tokens": response.usage.input_tokens,
            "completion_tokens": response.usage.output_tokens,
            "total_tokens": response.usage.input_tokens + response.usage.output_tokens,
        }

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            usage=usage,
            reasoning_content=reasoning_content,
            thinking_blocks=thinking_blocks or None,
        )

    def get_default_model(self) -> str:
        return self.default_model
