"""OpenAI-Compatible Provider — supports Responses with automatic fallback."""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any, Awaitable, Callable

import httpx
from loguru import logger

from bao.providers.api_mode_cache import get_cached_mode, set_cached_mode
from bao.providers.base import LLMProvider, LLMResponse, ToolCallRequest, normalize_tool_calls
from bao.providers.responses_compat import (
    append_responses_tool_call_arguments,
    build_responses_tool_call_request,
    convert_messages_to_responses,
    convert_tools_to_responses,
    parse_responses_json,
    replace_responses_tool_call_arguments,
    start_responses_tool_call,
)
from bao.providers.retry import (
    DEFAULT_BASE_DELAY,
    DEFAULT_MAX_RETRIES,
    ProgressCallbackError,
    StreamInterruptedError,
    emit_progress,
    emit_progress_reset,
    run_with_retries,
    safe_error_text,
)

_ALLOWED_MSG_KEYS = frozenset({"role", "content", "tool_calls", "tool_call_id", "name"})

_PROBE_FALLBACK_CODES = frozenset({404, 405, 501})
_MAX_RETRIES = DEFAULT_MAX_RETRIES
_BASE_DELAY = DEFAULT_BASE_DELAY

_CJK_CHAR_RE = re.compile(r"[\u3400-\u9FFF]")


def _normalize_openai_reasoning_effort(value: Any, *, allow_off: bool) -> str | None:
    if not isinstance(value, str):
        return None
    effort = value.strip().lower()
    if effort in {"low", "medium", "high"}:
        return effort
    if allow_off and effort == "off":
        return "none"
    return None


def _normalize_service_tier(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    service_tier = value.strip().lower()
    return service_tier or None


def _system_prompt_seems_ignored(system_prompt: str, content: str | None) -> bool:
    if not system_prompt:
        return False
    text = (content or "").strip()
    if not text:
        return False
    if "You are Bao" in system_prompt and re.search(r"\bCodex\b", text, re.I):
        return True
    if "Respond in 中文" in system_prompt and not _CJK_CHAR_RE.search(text):
        return True
    if re.search(r"what do you want to work on\?", text, re.I):
        return True
    return False


class _ResponsesHTTPStatusError(RuntimeError):
    def __init__(self, response: httpx.Response):
        self.status_code = response.status_code
        self.response = response
        super().__init__(f"Responses API HTTP {response.status_code}: {response.text[:500]}")


class OpenAICompatibleProvider(LLMProvider):
    """Universal OpenAI-compatible provider with automatic mode detection."""

    PROMPT_CACHING_PROVIDERS = frozenset({"openrouter", "openai"})

    def __init__(
        self,
        api_key: str | None = None,
        api_base: str | None = None,
        default_model: str = "gpt-4o",
        extra_headers: dict[str, str] | None = None,
        provider_name: str | None = None,
        model_prefix: str | None = None,
    ):
        super().__init__(api_key, api_base)
        self.default_model = default_model
        self.extra_headers = extra_headers or {}
        self.provider_name = provider_name or "openai"
        self._model_prefix = (model_prefix or "").strip().lower()
        self._effective_base = api_base or "https://api.openai.com/v1"

        headers = {"User-Agent": "Bao/1.0"}
        if self.extra_headers:
            headers.update(self.extra_headers)
        self._default_headers = headers
        self._api_key_str = api_key or "dummy-key"
        self._client: Any | None = None

    def _get_client(self) -> Any:
        client = self._client
        if client is None:
            from openai import AsyncOpenAI

            client = AsyncOpenAI(
                api_key=self._api_key_str,
                base_url=self._effective_base,
                default_headers=self._default_headers,
            )
            self._client = client
        return client

    def _resolve_model(self, model: str) -> str:
        if self._model_prefix and model.lower().startswith(f"{self._model_prefix}/"):
            return model.split("/", 1)[1]
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

    @staticmethod
    async def _iter_sse_events(response: httpx.Response):
        def _parse_buffer(lines: list[str]) -> dict[str, Any] | None:
            if not lines:
                return None
            data_lines = [item[5:].strip() for item in lines if item.startswith("data:")]
            if not data_lines:
                return None
            data = "\n".join(data_lines).strip()
            if not data or data == "[DONE]":
                return None
            try:
                event = json.loads(data)
            except Exception:
                return None
            return event if isinstance(event, dict) else None

        buffer: list[str] = []
        async for line in response.aiter_lines():
            if line == "":
                event = _parse_buffer(buffer)
                buffer = []
                if event is not None:
                    yield event
                continue
            buffer.append(line)

        event = _parse_buffer(buffer)
        if event is not None:
            yield event

    @staticmethod
    def _map_responses_finish_reason(status: str | None) -> str:
        return {
            "completed": "stop",
            "incomplete": "length",
            "failed": "error",
            "cancelled": "error",
        }.get(status or "completed", "stop")

    @staticmethod
    def _progress_callback_error_response(exc: ProgressCallbackError) -> LLMResponse:
        if isinstance(exc, StreamInterruptedError):
            return LLMResponse(content=None, finish_reason="interrupted")
        cause = exc.__cause__ or exc
        return LLMResponse(
            content=f"Error calling LLM progress callback: {safe_error_text(cause)}",
            finish_reason="error",
        )

    async def _consume_responses_stream(
        self,
        response: httpx.Response,
        on_progress: Callable[[str], Awaitable[None]] | None,
    ) -> LLMResponse:
        content = ""
        tool_calls: list[ToolCallRequest] = []
        tool_call_buffers: dict[str, dict[str, Any]] = {}
        finish_reason = "stop"
        usage: dict[str, int] = {}

        async for event in self._iter_sse_events(response):
            event_type = event.get("type")

            if event_type == "response.output_text.delta":
                delta = event.get("delta") or ""
                if delta:
                    content += delta
                    await emit_progress(on_progress, delta)
                continue

            if event_type == "response.output_item.added":
                item = event.get("item") or {}
                start_responses_tool_call(tool_call_buffers, item)
                continue

            if event_type == "response.function_call_arguments.delta":
                append_responses_tool_call_arguments(
                    tool_call_buffers, event.get("call_id"), event.get("delta")
                )
                continue

            if event_type == "response.function_call_arguments.done":
                replace_responses_tool_call_arguments(
                    tool_call_buffers, event.get("call_id"), event.get("arguments")
                )
                continue

            if event_type == "response.output_item.done":
                item = event.get("item") or {}
                tool_call = build_responses_tool_call_request(item, tool_call_buffers)
                if tool_call is not None:
                    tool_calls.append(tool_call)
                continue

            if event_type == "response.completed":
                response_obj = event.get("response") or {}
                finish_reason = self._map_responses_finish_reason(response_obj.get("status"))
                raw_usage = response_obj.get("usage")
                if isinstance(raw_usage, dict):
                    usage = {
                        "prompt_tokens": raw_usage.get("input_tokens", 0),
                        "completion_tokens": raw_usage.get("output_tokens", 0),
                        "total_tokens": raw_usage.get("total_tokens", 0),
                    }
                continue

            if event_type in {"error", "response.failed"}:
                raise RuntimeError("Responses stream failed")

        return LLMResponse(
            content=content or None,
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            usage=usage,
        )

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
        reasoning_effort = _normalize_openai_reasoning_effort(
            extra.get("reasoning_effort"), allow_off=True
        )
        if reasoning_effort is not None and not self._supports_reasoning_effort(resolved_model):
            reasoning_effort = None
        service_tier = _normalize_service_tier(extra.get("service_tier"))
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
                service_tier,
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
                service_tier,
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
            service_tier,
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
        service_tier: str | None = None,
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
        if service_tier:
            params["service_tier"] = service_tier

        content = ""
        retry_count = 0

        async def _on_retry(exc: BaseException, attempt: int, delay: float) -> None:
            nonlocal retry_count
            retry_count = attempt + 1
            await emit_progress_reset(on_progress)
            logger.warning(
                "⚠️ LLM 重试中 / retrying: transient error (attempt {}/{}), in {:.1f}s: {}",
                attempt + 1,
                _MAX_RETRIES + 1,
                delay,
                safe_error_text(exc),
            )

        async def _run_once() -> LLMResponse:
            nonlocal content
            content = ""
            stream = await self._get_client().chat.completions.create(**params)
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

            parsed_tools = []
            for idx in sorted(tool_calls_acc):
                tc = tool_calls_acc[idx]
                try:
                    args = json_repair.loads(tc["args"]) if tc["args"] else {}
                except Exception as exc:
                    raise RuntimeError("incomplete tool json in stream") from exc
                if not isinstance(args, dict):
                    args = {}
                parsed_tools.append(ToolCallRequest(id=tc["id"], name=tc["name"], arguments=args))

            return LLMResponse(
                content=content or None,
                tool_calls=parsed_tools,
                finish_reason=finish_reason,
                usage=usage,
                reasoning_content=reasoning_content,
            )

        try:
            return await run_with_retries(
                _run_once,
                max_retries=_MAX_RETRIES,
                base_delay=_BASE_DELAY,
                on_retry=_on_retry,
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
            if retry_count > 0:
                logger.error(
                    "❌ LLM 最终失败 / final failure: after {} attempts: {}",
                    retry_count + 1,
                    safe_error_text(e),
                )
            return LLMResponse(
                content=f"Error calling LLM: {safe_error_text(e)}",
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
        service_tier: str | None,
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
        if service_tier:
            body["service_tier"] = service_tier
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
        service_tier: str | None = None,
    ) -> LLMResponse:
        allow_fallback = True
        system_prompt, _ = convert_messages_to_responses(messages)
        body = self._build_responses_body(
            model,
            messages,
            tools,
            max_tokens,
            temperature,
            reasoning_effort,
            service_tier,
        )
        body["stream"] = True
        url = f"{self._effective_base.rstrip('/')}/responses"
        headers = self._build_responses_headers()
        retry_count = 0

        async def _on_retry(exc: BaseException, attempt: int, delay: float) -> None:
            nonlocal retry_count
            retry_count = attempt + 1
            logger.warning(
                "⚠️ 接口重试中 / retrying: [{}] Responses transient error (attempt {}/{}), in {:.1f}s: {}",
                source,
                attempt + 1,
                _MAX_RETRIES + 1,
                delay,
                safe_error_text(exc),
            )

        async def _run_once() -> LLMResponse:
            try:
                await emit_progress_reset(on_progress)
            except ProgressCallbackError:
                raise
            try:
                async with httpx.AsyncClient(timeout=120.0) as client:
                    async with client.stream("POST", url, headers=headers, json=body) as resp:
                        if resp.status_code == 200:
                            result = await self._consume_responses_stream(resp, on_progress)
                            if allow_fallback and _system_prompt_seems_ignored(
                                system_prompt, result.content
                            ):
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
                                    service_tier,
                                )
                            return result

                        status_err = _ResponsesHTTPStatusError(resp)
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
                                service_tier,
                            )
                        raise status_err
            except asyncio.CancelledError:
                raise
        try:
            return await run_with_retries(
                _run_once,
                max_retries=_MAX_RETRIES,
                base_delay=_BASE_DELAY,
                on_retry=_on_retry,
            )
        except asyncio.CancelledError:
            raise
        except ProgressCallbackError as exc:
            return self._progress_callback_error_response(exc)
        except Exception as exc:
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
                    service_tier,
                )
            if retry_count > 0:
                logger.error(
                    "❌ Responses 最终失败 / final failure: after {} attempts: {}",
                    retry_count + 1,
                    safe_error_text(exc),
                )
            return LLMResponse(
                content=f"Error calling Responses API: {safe_error_text(exc)}",
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
        service_tier: str | None = None,
    ) -> LLMResponse:
        system_prompt, _ = convert_messages_to_responses(messages)
        body = self._build_responses_body(
            model,
            messages,
            tools,
            max_tokens,
            temperature,
            reasoning_effort,
            service_tier,
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
                    service_tier,
                )

            if resp.status_code == 200:
                result = self._build_responses_result(self._decode_responses_payload(resp))
                if _system_prompt_seems_ignored(system_prompt, result.content):
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
                        service_tier,
                    )
                set_cached_mode(self._effective_base, "responses")
                logger.info("🤖 响应已启用 / detected: [{}] Responses API cached", source)
                return result

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
                service_tier,
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
                service_tier,
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
