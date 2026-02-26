"""Google Gemini Provider — native SDK with Thinking Mode support."""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from google import genai
from google.genai import types

from bao.providers.base import LLMProvider, LLMResponse, ToolCallRequest


class GeminiProvider(LLMProvider):
    """
    Google Gemini provider using the official google-genai SDK.

    Supports:
    - Gemini 2.0 Flash, 2.5 Flash, 2.5 Pro
    - Thinking Mode (Gemini 2.5 models)
    - Function calling
    - Structured outputs

    Models: gemini-2.0-flash, gemini-2.5-flash-preview-05-20, gemini-2.5-pro-preview-05-20, etc.
    """

    def __init__(
        self,
        api_key: str | None = None,
        default_model: str = "gemini-2.0-flash",
        base_url: str | None = None,
    ):
        super().__init__(api_key, None)
        self.default_model = default_model
        client_kwargs: dict[str, Any] = {"api_key": api_key}
        if base_url:
            client_kwargs["http_options"] = types.HttpOptions(base_url=base_url)
        self._client = genai.Client(**client_kwargs)

    def _resolve_model(self, model: str) -> str:
        """Strip provider prefix (e.g. 'gemini/', 'custom/') if present."""
        if "/" in model:
            return model.split("/", 1)[1]
        return model

    def _convert_messages(self, messages: list[dict[str, Any]]) -> list[types.Content]:
        """Convert OpenAI-style messages to Gemini format (Content objects)."""
        import base64 as _b64mod

        contents: list[types.Content] = []
        pending_images: list[str] = []

        for msg in messages:
            role = msg.get("role")
            content = msg.get("content")

            # Map OpenAI roles to Gemini roles
            if role == "system":
                continue

            gemini_role = "user" if role in ("user", "system") else "model"

            # Flush pending screenshot images before non-tool message
            if role != "tool" and pending_images:
                img_parts = [types.Part(text="[screenshot from tool above]")]
                for ib64 in pending_images:
                    img_parts.append(types.Part(inline_data=types.Blob(
                        mime_type="image/jpeg",
                        data=_b64mod.b64decode(ib64),
                    )))
                contents.append(types.Content(role="user", parts=img_parts))
                pending_images = []

            # Handle content
            if isinstance(content, str):
                parts = [types.Part(text=content)]
            elif isinstance(content, list):
                parts = []
                for item in content:
                    if not isinstance(item, dict):
                        continue
                    item_type = item.get("type")
                    if item_type == "text":
                        parts.append(types.Part(text=item.get("text", "")))
                    elif item_type == "image_url":
                        url_data = item.get("image_url") or {}
                        url = url_data.get("url", "")
                        # For now, skip image handling - would need to fetch
            else:
                parts = [types.Part(text=str(content) if content else "")]

            # Handle tool calls (function calling)
            tool_calls = msg.get("tool_calls", [])
            if tool_calls:
                for tc in tool_calls:
                    fn = tc.get("function") or {}
                    parts.append(
                        types.Part(
                            function_call=types.FunctionCall(
                                name=fn.get("name", ""),
                                args=fn.get("arguments", {}),
                            )
                        )
                    )

            if parts:
                contents.append(types.Content(role=gemini_role, parts=parts))
                # Collect screenshot image for deferred injection
                img_b64 = msg.get("_image")
                if img_b64 and role == "tool":
                    pending_images.append(img_b64)

        # Flush any remaining images at end
        if pending_images:
            img_parts = [types.Part(text="[screenshot from tool above]")]
            for ib64 in pending_images:
                img_parts.append(types.Part(inline_data=types.Blob(
                    mime_type="image/jpeg",
                    data=_b64mod.b64decode(ib64),
                )))
            contents.append(types.Content(role="user", parts=img_parts))

        return contents

    def _convert_tools(self, tools: list[dict[str, Any]]) -> list[types.Tool]:
        """Convert OpenAI function-calling tools to Gemini Tool format."""
        gemini_tools = []

        for tool in tools:
            fn = (tool.get("function") or {}) if tool.get("type") == "function" else tool
            name = fn.get("name")
            if not name:
                continue

            description = fn.get("description", "")
            parameters = fn.get("parameters") or {}

            gemini_tools.append(
                types.Tool(
                    function_declarations=[
                        types.FunctionDeclaration(
                            name=name,
                            description=description,
                            parameters=parameters if isinstance(parameters, dict) else {},
                        )
                    ]
                )
            )

        return gemini_tools

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
        Send a chat completion request via Gemini API.

        Args:
            messages: List of message dicts with 'role' and 'content'.
            tools: Optional list of tool definitions in OpenAI format.
            model: Model identifier (e.g., 'gemini-2.0-flash').
            max_tokens: Maximum tokens in response.
            temperature: Sampling temperature.

        Returns:
            LLMResponse with content and/or tool calls.
        """
        original_model = model or self.default_model
        resolved_model = self._resolve_model(original_model)

        # Extract system prompt
        system_prompt = None
        filtered_messages = []
        for msg in messages:
            if msg.get("role") == "system":
                system_prompt = msg.get("content")
            else:
                filtered_messages.append(msg)

        # Convert messages
        contents = self._convert_messages(filtered_messages)

        # Prepare config
        config = types.GenerateContentConfig(
            max_output_tokens=max_tokens,
            temperature=temperature,
            system_instruction=system_prompt,
        )

        # Add tools if provided
        if tools:
            config.tools = self._convert_tools(tools)

        # Handle thinking (Gemini 2.5 thinking mode)
        thinking = kwargs.get("thinking", False)
        if thinking:
            # Gemini uses thinking config
            config.thinking_config = types.ThinkingConfig(
                include_thoughts=True,
                thinking_budget=kwargs.get("thinking_budget", 2048),
            )

        try:
            content = ""
            tool_calls: list[ToolCallRequest] = []
            reasoning_content: str | None = None
            chunk = None
            async for chunk in await self._client.aio.models.generate_content_stream(
                model=resolved_model,
                contents=contents,
                config=config,
            ):
                if not chunk.candidates:
                    continue
                candidate = chunk.candidates[0]
                if not candidate.content or not candidate.content.parts:
                    continue
                for part in candidate.content.parts:
                    if part.text:
                        content += part.text
                        if on_progress:
                            await on_progress(part.text)
                    if getattr(part, "thought", None):
                        reasoning_content = (reasoning_content or "") + str(part.thought)
                    if part.function_call:
                        fc = part.function_call
                        args_dict = {}
                        if fc.args:
                            args_dict = dict(fc.args) if isinstance(fc.args, dict) else {}
                        tool_calls.append(ToolCallRequest(
                            id=getattr(fc, "id", None) or f"call_{fc.name}",
                            name=fc.name or "unknown",
                            arguments=args_dict,
                        ))
            # Finish reason from last chunk
            finish_reason = "stop"
            if chunk and chunk.candidates:
                fr = str(chunk.candidates[0].finish_reason)
                finish_reason = {
                    "STOP": "stop", "MAX_TOKENS": "length",
                    "SAFETY": "content_filter", "RECITATION": "content_filter",
                }.get(fr, "stop")
            # Usage from last chunk
            usage: dict[str, int] = {}
            if chunk and hasattr(chunk, "usage_metadata") and chunk.usage_metadata:
                um = chunk.usage_metadata
                usage = {
                    "prompt_tokens": getattr(um, "prompt_token_count", 0),
                    "completion_tokens": getattr(um, "candidates_token_count", 0),
                    "total_tokens": getattr(um, "total_token_count", 0),
                }
            return LLMResponse(
                content=content or None,
                tool_calls=tool_calls,
                finish_reason=finish_reason,
                usage=usage,
                reasoning_content=reasoning_content,
            )
        except Exception as e:
            return LLMResponse(
                content=f"Error calling Gemini: {str(e)}",
                finish_reason="error",
            )

    def _parse_response(self, response: Any) -> LLMResponse:
        """Parse Gemini response into LLMResponse."""
        content = ""
        tool_calls: list[ToolCallRequest] = []
        reasoning_content: str | None = None

        # Get candidates
        candidates = getattr(response, "candidates", [])
        if not candidates:
            return LLMResponse(
                content="No response from Gemini",
                finish_reason="error",
            )

        candidate = candidates[0]
        finish_reason_map = {
            "STOP": "stop",
            "MAX_TOKENS": "length",
            "SAFETY": "content_filter",
            "RECITATION": "content_filter",
            "OTHER": "error",
        }
        finish_reason = finish_reason_map.get(str(candidate.finish_reason), "stop")

        # Get content
        if candidate.content and candidate.content.parts:
            for part in candidate.content.parts:
                if part.text:
                    content += part.text
                if part.thought:
                    # Gemini thinking thoughts
                    reasoning_content = (reasoning_content or "") + part.thought
                if part.function_call:
                    # Function call
                    fc = part.function_call
                    args_dict = {}
                    if fc.args:
                        # args can be a dict or a JSON string
                        if isinstance(fc.args, dict):
                            args_dict = fc.args
                        else:
                            import json

                            try:
                                args_dict = json.loads(fc.args)
                            except:
                                args_dict = {"raw": str(fc.args)}

                    tool_calls.append(
                        ToolCallRequest(
                            id=fc.id or f"call_{fc.name}",
                            name=fc.name,
                            arguments=args_dict,
                        )
                    )

        # Usage
        usage = {}
        if hasattr(response, "usage_metadata"):
            um = response.usage_metadata
            usage = {
                "prompt_tokens": getattr(um, "prompt_token_count", 0),
                "completion_tokens": getattr(um, "candidates_token_count", 0),
                "total_tokens": getattr(um, "total_token_count", 0),
            }

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            usage=usage,
            reasoning_content=reasoning_content,
        )

    def get_default_model(self) -> str:
        return self.default_model
