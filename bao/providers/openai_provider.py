"""OpenAI-Compatible Provider — supports Chat Completions and Responses API with auto-detection."""

from __future__ import annotations

import asyncio
import json
from typing import Any, Awaitable, Callable

import httpx
from loguru import logger
from openai import AsyncOpenAI

from bao.providers.api_mode_cache import get_cached_mode, set_cached_mode
from bao.providers.base import LLMProvider, LLMResponse, normalize_tool_calls
from bao.providers.responses_compat import (
    convert_messages_to_responses,
    convert_tools_to_responses,
    parse_responses_json,
)
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

_ALLOWED_MSG_KEYS = frozenset({"role", "content", "tool_calls", "tool_call_id", "name"})

_PROBE_FALLBACK_CODES = frozenset({404, 405, 501})
_MAX_RETRIES = DEFAULT_MAX_RETRIES
_BASE_DELAY = DEFAULT_BASE_DELAY


class _ResponsesHTTPStatusError(RuntimeError):
    def __init__(self, response: httpx.Response):
        self.status_code = response.status_code
        self.response = response
        super().__init__(f"Responses API HTTP {response.status_code}: {response.text[:500]}")


class OpenAICompatibleProvider(LLMProvider):
    """Universal OpenAI-compatible provider with Responses API auto-detection.

    When api_mode is "auto" (default), the first request probes the Responses API.
    If supported, all subsequent requests use it; otherwise falls back to Chat Completions.
    The detection result is cached per endpoint to disk with a 7-day TTL.
    """

    PROMPT_CACHING_PROVIDERS = frozenset({"openrouter", "openai"})

    def __init__(
        self,
        api_key: str | None = None,
        api_base: str | None = None,
        default_model: str = "gpt-4o",
        extra_headers: dict[str, str] | None = None,
        provider_name: str | None = None,
        api_mode: str = "auto",
        model_prefix: str | None = None,
    ):
        super().__init__(api_key, api_base)
        self.default_model = default_model
        self.extra_headers = extra_headers or {}
        self.provider_name = provider_name or "openai"
        self._api_mode = api_mode
        self._model_prefix = (model_prefix or "").strip().lower()
        self._effective_base = api_base or "https://api.openai.com/v1"

        headers = {"User-Agent": "bao/1.0"}
        if self.extra_headers:
            headers.update(self.extra_headers)
        self._default_headers = headers
        self._api_key_str = api_key or "dummy-key"

        self._client = AsyncOpenAI(
            api_key=self._api_key_str,
            base_url=self._effective_base,
            default_headers=headers,
        )

    def _resolve_model(self, model: str) -> str:
        if self._model_prefix and model.lower().startswith(f"{self._model_prefix}/"):
            return model.split("/", 1)[1]
        prefixes_to_strip = (
            "openrouter/",
            "deepseek/",
            "groq/",
            "anthropic/",
            "gemini/",
            "moonshot/",
            "minimax/",
            "qwen/",
            "glm/",
            "zhipu/",
            "vllm/",
            "ollama/",
            "lm-studio/",
        )
        model_lower = model.lower()
        for prefix in prefixes_to_strip:
            if model_lower.startswith(prefix):
                return model[len(prefix) :]
        return model

    @staticmethod
    def _supports_reasoning_effort(model: str) -> bool:
        m = model.lower()
        prefixes = ("gpt-5", "o1", "o3", "o4")
        return m.startswith(prefixes)

    def _supports_prompt_caching(self) -> bool:
        return self.provider_name.lower() in self.PROMPT_CACHING_PROVIDERS

    def _apply_cache_control(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]] | None]:
        if not self._supports_prompt_caching():
            return messages, tools

        new_messages = []
        for msg in messages:
            if msg.get("role") == "system":
                content = msg["content"]
                if isinstance(content, str):
                    new_content = [
                        {"type": "text", "text": content, "cache_control": {"type": "ephemeral"}}
                    ]
                elif isinstance(content, list) and content:
                    new_content = list(content)
                    last_block = new_content[-1]
                    if isinstance(last_block, dict):
                        new_content[-1] = {**last_block, "cache_control": {"type": "ephemeral"}}
                    else:
                        new_content.append(
                            {
                                "type": "text",
                                "text": str(last_block),
                                "cache_control": {"type": "ephemeral"},
                            }
                        )
                elif isinstance(content, list):
                    new_content = [
                        {
                            "type": "text",
                            "text": "",
                            "cache_control": {"type": "ephemeral"},
                        }
                    ]
                else:
                    new_content = [
                        {
                            "type": "text",
                            "text": str(content or ""),
                            "cache_control": {"type": "ephemeral"},
                        }
                    ]
                new_messages.append({**msg, "content": new_content})
            else:
                new_messages.append(msg)

        new_tools = tools
        if tools:
            new_tools = list(tools)
            new_tools[-1] = {**new_tools[-1], "cache_control": {"type": "ephemeral"}}

        return new_messages, new_tools

    @staticmethod
    def _sanitize_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        sanitized: list[dict[str, Any]] = []
        pending_images: list[str] = []
        for msg in messages:
            img_b64 = msg.get("_image")
            clean = {k: v for k, v in msg.items() if k in _ALLOWED_MSG_KEYS}
            if clean.get("role") == "tool":
                clean.pop("name", None)
            if clean.get("role") == "assistant" and "content" not in clean:
                clean["content"] = None
            # Flush pending screenshot images before non-tool message
            if clean.get("role") != "tool" and pending_images:
                parts: list[dict[str, Any]] = [
                    {"type": "text", "text": "[screenshot from tool above]"}
                ]
                for ib64 in pending_images:
                    parts.append(
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{ib64}"},
                        }
                    )
                sanitized.append({"role": "user", "content": parts})
                pending_images = []
            sanitized.append(clean)
            if img_b64 and clean.get("role") == "tool":
                pending_images.append(img_b64)
        # Flush any remaining images at end of messages
        if pending_images:
            parts = [{"type": "text", "text": "[screenshot from tool above]"}]
            for ib64 in pending_images:
                parts.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{ib64}"},
                    }
                )
            sanitized.append({"role": "user", "content": parts})
        return sanitized

    def _resolve_effective_mode(self) -> str:
        if self._api_mode in {"responses", "completions"}:
            return self._api_mode
        return get_cached_mode(self._effective_base) or "auto"

    @staticmethod
    def _build_responses_result(payload: dict[str, Any]) -> LLMResponse:
        content, tool_calls, finish_reason, usage = parse_responses_json(payload)
        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            usage=usage,
        )

    @staticmethod
    def _decode_responses_payload(resp: httpx.Response) -> dict[str, Any]:
        try:
            payload = resp.json()
            if isinstance(payload, dict):
                return payload
        except Exception:
            pass

        latest_response: dict[str, Any] | None = None
        for raw_line in (resp.text or "").splitlines():
            line = raw_line.strip()
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if not data or data == "[DONE]":
                continue
            try:
                event = json.loads(data)
            except Exception:
                continue
            if not isinstance(event, dict):
                continue
            if isinstance(event.get("response"), dict):
                latest_response = event["response"]
                if event.get("type") == "response.completed":
                    break
            elif event.get("object") == "response":
                latest_response = event

        if latest_response is None:
            raise ValueError("Cannot decode Responses payload")
        return latest_response

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        on_progress: Callable[[str], Awaitable[None]] | None = None,
        **extra: Any,
    ) -> LLMResponse:
        original_model = model or self.default_model
        resolved_model = self._resolve_model(original_model)

        if self._supports_prompt_caching():
            messages, tools = self._apply_cache_control(messages, tools)

        max_tokens = max(1, max_tokens)
        source = str(extra.get("source", "main"))
        reasoning_effort = extra.get("reasoning_effort")
        if not isinstance(reasoning_effort, str):
            reasoning_effort = None
        if reasoning_effort is not None:
            effort = reasoning_effort.strip().lower()
            reasoning_effort = effort if effort in {"low", "medium", "high"} else None
        if reasoning_effort is not None and not self._supports_reasoning_effort(resolved_model):
            reasoning_effort = None
        mode = self._resolve_effective_mode()

        if mode == "responses":
            return await self._chat_responses(
                resolved_model,
                messages,
                tools,
                max_tokens,
                temperature,
                on_progress,
                source,
                reasoning_effort,
            )
        if mode == "completions":
            return await self._chat_completions(
                resolved_model,
                messages,
                tools,
                max_tokens,
                temperature,
                on_progress,
                source,
                reasoning_effort,
            )

        return await self._chat_with_probe(
            resolved_model,
            messages,
            tools,
            max_tokens,
            temperature,
            on_progress,
            source,
            reasoning_effort,
        )

    async def _chat_completions(
        self,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        max_tokens: int,
        temperature: float,
        on_progress: Callable[[str], Awaitable[None]] | None = None,
        source: str = "main",
        reasoning_effort: str | None = None,
    ) -> LLMResponse:
        del source
        params: dict[str, Any] = {
            "model": model,
            "messages": self._sanitize_messages(messages),
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True,
        }
        if tools:
            params["tools"] = tools
            params["tool_choice"] = "auto"
        if reasoning_effort:
            params["reasoning_effort"] = reasoning_effort

        last_err: Exception | None = None
        content = ""
        for attempt in range(_MAX_RETRIES + 1):
            try:
                content = ""
                stream = await self._client.chat.completions.create(**params)
                tool_calls_acc: dict[int, dict[str, Any]] = {}
                finish_reason = "stop"
                usage: dict[str, int] = {}
                reasoning_content: str | None = None

                async for chunk in stream:
                    if not chunk.choices:
                        if hasattr(chunk, "usage") and chunk.usage:
                            usage = {
                                "prompt_tokens": chunk.usage.prompt_tokens or 0,
                                "completion_tokens": chunk.usage.completion_tokens or 0,
                                "total_tokens": chunk.usage.total_tokens or 0,
                            }
                        continue
                    delta = chunk.choices[0].delta
                    if delta.content:
                        content += delta.content
                        await emit_progress(on_progress, delta.content)
                    rc = getattr(delta, "reasoning_content", None)
                    if rc:
                        if reasoning_content is None:
                            reasoning_content = ""
                        reasoning_content += rc
                    if delta.tool_calls:
                        for tc in delta.tool_calls:
                            idx = tc.index
                            if idx not in tool_calls_acc:
                                tool_calls_acc[idx] = {
                                    "id": tc.id or "",
                                    "name": tc.function.name or "",
                                    "args": "",
                                }
                            if tc.function and tc.function.arguments:
                                tool_calls_acc[idx]["args"] += tc.function.arguments
                            if tc.id:
                                tool_calls_acc[idx]["id"] = tc.id
                            if tc.function and tc.function.name:
                                tool_calls_acc[idx]["name"] = tc.function.name
                    if chunk.choices[0].finish_reason:
                        finish_reason = chunk.choices[0].finish_reason

                import json_repair

                from bao.providers.base import ToolCallRequest

                parsed_tools = []
                for idx in sorted(tool_calls_acc):
                    tc = tool_calls_acc[idx]
                    try:
                        args = json_repair.loads(tc["args"]) if tc["args"] else {}
                    except Exception as exc:
                        raise RuntimeError("incomplete tool json in stream") from exc
                    if not isinstance(args, dict):
                        args = {}
                    parsed_tools.append(
                        ToolCallRequest(id=tc["id"], name=tc["name"], arguments=args)
                    )

                return LLMResponse(
                    content=content or None,
                    tool_calls=parsed_tools,
                    finish_reason=finish_reason,
                    usage=usage,
                    reasoning_content=reasoning_content,
                )
            except asyncio.CancelledError:
                raise
            except ProgressCallbackError as exc:
                if isinstance(exc, StreamInterruptedError):
                    return LLMResponse(content=content or None, finish_reason="interrupted")
                cause = exc.__cause__ or exc
                return LLMResponse(
                    content=f"Error calling LLM progress callback: {safe_error_text(cause)}",
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
                            content=f"Error calling LLM progress callback: {safe_error_text(cause)}",
                            finish_reason="error",
                        )

                    delay = compute_retry_delay(e, attempt, base_delay=_BASE_DELAY)
                    logger.warning(
                        "⚠️ LLM 重试中 / retrying: transient error (attempt {}/{}), in {:.1f}s: {}",
                        attempt + 1,
                        _MAX_RETRIES + 1,
                        delay,
                        safe_error_text(e),
                    )
                    await asyncio.sleep(delay)
                    continue
                if attempt > 0:
                    logger.error(
                        "❌ LLM 最终失败 / final failure: after {} attempts: {}",
                        attempt + 1,
                        safe_error_text(e),
                    )
                return LLMResponse(
                    content=f"Error calling LLM: {safe_error_text(e)}",
                    finish_reason="error",
                )
        return LLMResponse(
            content=f"Error calling LLM: {safe_error_text(last_err or RuntimeError('unknown error'))}",
            finish_reason="error",
        )

    def _build_responses_body(
        self,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        max_tokens: int,
        temperature: float,
        reasoning_effort: str | None,
    ) -> dict[str, Any]:
        system_prompt, input_items = convert_messages_to_responses(messages)
        body: dict[str, Any] = {
            "model": model,
            "input": input_items,
            "temperature": temperature,
            "max_output_tokens": max_tokens,
            "store": False,
        }
        if system_prompt:
            body["instructions"] = system_prompt
        if tools:
            body["tools"] = convert_tools_to_responses(tools)
            body["tool_choice"] = "auto"
        if reasoning_effort:
            body["reasoning"] = {"effort": reasoning_effort}
        return body

    def _build_responses_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key_str}",
            "Content-Type": "application/json",
            **self._default_headers,
        }

    async def _chat_responses(
        self,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        max_tokens: int,
        temperature: float,
        on_progress: Callable[[str], Awaitable[None]] | None = None,
        source: str = "main",
        reasoning_effort: str | None = None,
    ) -> LLMResponse:
        allow_fallback = self._api_mode == "auto"
        body = self._build_responses_body(
            model,
            messages,
            tools,
            max_tokens,
            temperature,
            reasoning_effort,
        )
        url = f"{self._effective_base.rstrip('/')}/responses"
        headers = self._build_responses_headers()

        last_err: Exception | None = None
        for attempt in range(_MAX_RETRIES + 1):
            try:
                await emit_progress_reset(on_progress)
            except ProgressCallbackError as exc:
                if isinstance(exc, StreamInterruptedError):
                    return LLMResponse(content=None, finish_reason="interrupted")
                cause = exc.__cause__ or exc
                return LLMResponse(
                    content=f"Error calling LLM progress callback: {safe_error_text(cause)}",
                    finish_reason="error",
                )
            try:
                async with httpx.AsyncClient(timeout=120.0) as client:
                    resp = await client.post(url, headers=headers, json=body)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                last_err = exc
                if should_retry_exception(exc) and attempt < _MAX_RETRIES:
                    delay = compute_retry_delay(exc, attempt, base_delay=_BASE_DELAY)
                    logger.warning(
                        "⚠️ 接口重试中 / retrying: [{}] Responses transient error (attempt {}/{}), in {:.1f}s: {}",
                        source,
                        attempt + 1,
                        _MAX_RETRIES + 1,
                        delay,
                        safe_error_text(exc),
                    )
                    await asyncio.sleep(delay)
                    continue

                if allow_fallback:
                    logger.debug(
                        "🤖 回退补全 / fallback: [{}] request failed model={} base={} ({}), trying Chat Completions",
                        source,
                        model,
                        self._effective_base,
                        safe_error_text(exc),
                    )
                    return await self._chat_completions(
                        model,
                        messages,
                        tools,
                        max_tokens,
                        temperature,
                        on_progress,
                        source,
                        reasoning_effort,
                    )

                return LLMResponse(
                    content=f"Error calling Responses API: {safe_error_text(exc)}",
                    finish_reason="error",
                )

            if resp.status_code == 200:
                try:
                    return self._build_responses_result(self._decode_responses_payload(resp))
                except Exception as exc:
                    parse_err = RuntimeError("incomplete responses payload")
                    parse_err.__cause__ = exc
                    last_err = parse_err
                    if attempt < _MAX_RETRIES:
                        delay = compute_retry_delay(parse_err, attempt, base_delay=_BASE_DELAY)
                        logger.warning(
                            "⚠️ 负载重试中 / retrying: [{}] payload parse failed (attempt {}/{}), in {:.1f}s: {}",
                            source,
                            attempt + 1,
                            _MAX_RETRIES + 1,
                            delay,
                            safe_error_text(exc),
                        )
                        await asyncio.sleep(delay)
                        continue

                    if allow_fallback:
                        logger.debug(
                            "🤖 回退补全 / fallback: [{}] payload parse failed model={} base={} ({}), trying Chat Completions",
                            source,
                            model,
                            self._effective_base,
                            safe_error_text(exc),
                        )
                        return await self._chat_completions(
                            model,
                            messages,
                            tools,
                            max_tokens,
                            temperature,
                            on_progress,
                            source,
                            reasoning_effort,
                        )

                    return LLMResponse(
                        content=f"Error calling Responses API: {safe_error_text(parse_err)}",
                        finish_reason="error",
                    )

            status_err = _ResponsesHTTPStatusError(resp)
            last_err = status_err
            if resp.status_code in _PROBE_FALLBACK_CODES and allow_fallback:
                logger.debug(
                    "🤖 响应不支持 / unsupported: [{}] status {}, falling back to Chat Completions",
                    source,
                    resp.status_code,
                )
                set_cached_mode(self._effective_base, "completions")
                return await self._chat_completions(
                    model,
                    messages,
                    tools,
                    max_tokens,
                    temperature,
                    on_progress,
                    source,
                    reasoning_effort,
                )

            if should_retry_exception(status_err) and attempt < _MAX_RETRIES:
                delay = compute_retry_delay(status_err, attempt, base_delay=_BASE_DELAY)
                logger.warning(
                    "⚠️ HTTP 重试中 / retrying: [{}] transient HTTP {} (attempt {}/{}), in {:.1f}s",
                    source,
                    resp.status_code,
                    attempt + 1,
                    _MAX_RETRIES + 1,
                    delay,
                )
                await asyncio.sleep(delay)
                continue

            if allow_fallback:
                logger.debug(
                    "🤖 回退补全 / fallback: [{}] Responses returned {} model={} base={}, trying Chat Completions",
                    source,
                    resp.status_code,
                    model,
                    self._effective_base,
                )
                return await self._chat_completions(
                    model,
                    messages,
                    tools,
                    max_tokens,
                    temperature,
                    on_progress,
                    source,
                    reasoning_effort,
                )

            return LLMResponse(
                content=f"Error calling Responses API: {safe_error_text(status_err)}",
                finish_reason="error",
            )

        return LLMResponse(
            content=(
                "Error calling Responses API: "
                f"{safe_error_text(last_err or RuntimeError('unknown error'))}"
            ),
            finish_reason="error",
        )

    async def _chat_with_probe(
        self,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        max_tokens: int,
        temperature: float,
        on_progress: Callable[[str], Awaitable[None]] | None = None,
        source: str = "main",
        reasoning_effort: str | None = None,
    ) -> LLMResponse:
        body = self._build_responses_body(
            model,
            messages,
            tools,
            max_tokens,
            temperature,
            reasoning_effort,
        )
        url = f"{self._effective_base.rstrip('/')}/responses"
        headers = self._build_responses_headers()

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(url, headers=headers, json=body)

            if resp.status_code in _PROBE_FALLBACK_CODES:
                logger.debug(
                    "🤖 探测回退 / probe fallback: [{}] Responses not supported ({}), falling back",
                    source,
                    resp.status_code,
                )
                set_cached_mode(self._effective_base, "completions")
                return await self._chat_completions(
                    model,
                    messages,
                    tools,
                    max_tokens,
                    temperature,
                    on_progress,
                    source,
                    reasoning_effort,
                )

            if resp.status_code == 200:
                set_cached_mode(self._effective_base, "responses")
                logger.info("🤖 响应已启用 / detected: [{}] Responses API cached", source)
                return self._build_responses_result(self._decode_responses_payload(resp))

            logger.debug(
                "🤖 探测回退 / probe fallback: [{}] Responses returned {} model={} base={}, trying Chat Completions",
                source,
                resp.status_code,
                model,
                self._effective_base,
            )
            return await self._chat_completions(
                model,
                messages,
                tools,
                max_tokens,
                temperature,
                on_progress,
                source,
                reasoning_effort,
            )

        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.debug(
                "🤖 探测失败回退 / probe fallback: [{}] probe failed model={} base={} ({}), trying Chat Completions",
                source,
                model,
                self._effective_base,
                e,
            )
            return await self._chat_completions(
                model,
                messages,
                tools,
                max_tokens,
                temperature,
                on_progress,
                source,
                reasoning_effort,
            )

    def _parse_completions_response(self, response: Any) -> LLMResponse:
        choice = response.choices[0]
        message = choice.message

        tool_calls = normalize_tool_calls(message)

        usage = {}
        raw_usage = getattr(response, "usage", None)
        if raw_usage:
            usage = {
                "prompt_tokens": raw_usage.prompt_tokens,
                "completion_tokens": raw_usage.completion_tokens,
                "total_tokens": raw_usage.total_tokens,
            }

        reasoning_content = getattr(message, "reasoning_content", None)

        return LLMResponse(
            content=message.content,
            tool_calls=tool_calls,
            finish_reason=choice.finish_reason or "stop",
            usage=usage,
            reasoning_content=reasoning_content,
        )

    def get_default_model(self) -> str:
        return self.default_model
