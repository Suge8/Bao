from __future__ import annotations

import asyncio
import email.utils
import time
from collections.abc import Awaitable, Callable, Iterable

try:
    import httpx
except Exception:
    httpx = None


DEFAULT_RETRYABLE_KEYWORDS = (
    "connection",
    "incomplete",
    "chunked",
    "timeout",
    "timed out",
    "overloaded",
    "bad gateway",
    "service unavailable",
    "internal server error",
    "eof",
    "reset by peer",
    "broken pipe",
    "rate limit",
    "too many requests",
)

NON_RETRYABLE_KEYWORDS = (
    "invalid api key",
    "authentication",
    "unauthorized",
    "forbidden",
    "permission denied",
    "invalid_request_error",
    "bad request",
)

RETRYABLE_STATUS_CODES = frozenset({408, 409, 425, 429, 500, 502, 503, 504})
MAX_RETRY_AFTER_SECONDS = 60.0
DEFAULT_MAX_RETRIES = 2
DEFAULT_BASE_DELAY = 1.0
PROGRESS_RESET = "\x00"


class ProgressCallbackError(RuntimeError):
    pass


class StreamInterruptedError(ProgressCallbackError):
    """Raised when soft interrupt is detected during LLM streaming."""

    pass


def safe_error_text(exc: BaseException) -> str:
    try:
        text = str(exc)
    except Exception:
        text = exc.__class__.__name__
    return text or exc.__class__.__name__


def iter_exception_chain(exc: BaseException) -> Iterable[BaseException]:
    seen: set[int] = set()
    stack: list[BaseException] = [exc]

    while stack:
        cur = stack.pop()
        key = id(cur)
        if key in seen:
            continue
        seen.add(key)
        yield cur

        if isinstance(cur, BaseExceptionGroup):
            stack.extend(cur.exceptions)

        cause = getattr(cur, "__cause__", None)
        if isinstance(cause, BaseException):
            stack.append(cause)

        context = getattr(cur, "__context__", None)
        if isinstance(context, BaseException):
            stack.append(context)


def _extract_status_code(exc: BaseException) -> int | None:
    for attr in ("status_code", "status"):
        raw = getattr(exc, attr, None)
        if isinstance(raw, int):
            return raw
        if isinstance(raw, str) and raw.isdigit():
            return int(raw)

    response = getattr(exc, "response", None)
    if response is not None:
        status_code = getattr(response, "status_code", None)
        if isinstance(status_code, int):
            return status_code
    return None


def _parse_retry_after(raw: str) -> float | None:
    text = raw.strip()
    if not text:
        return None

    try:
        return max(0.0, float(text))
    except ValueError:
        pass

    try:
        dt = email.utils.parsedate_to_datetime(text)
    except Exception:
        return None
    if dt is None:
        return None

    if dt.tzinfo is None:
        return None

    return max(0.0, dt.timestamp() - time.time())


def _extract_retry_after(exc: BaseException) -> float | None:
    for error in iter_exception_chain(exc):
        retry_after = getattr(error, "retry_after", None)
        if isinstance(retry_after, (int, float)):
            return max(0.0, float(retry_after))
        if isinstance(retry_after, str):
            parsed = _parse_retry_after(retry_after)
            if parsed is not None:
                return parsed

        response = getattr(error, "response", None)
        headers = getattr(response, "headers", None)
        if headers and hasattr(headers, "get"):
            raw = headers.get("retry-after")
            if isinstance(raw, str):
                parsed = _parse_retry_after(raw)
                if parsed is not None:
                    return parsed
    return None


def should_retry_exception(
    exc: BaseException,
    *,
    retryable_keywords: tuple[str, ...] = DEFAULT_RETRYABLE_KEYWORDS,
) -> bool:
    status_codes: list[int] = []
    messages: list[str] = []

    for error in iter_exception_chain(exc):
        if isinstance(error, (asyncio.CancelledError, KeyboardInterrupt, SystemExit)):
            return False

        status = _extract_status_code(error)
        if status is not None:
            status_codes.append(status)

        messages.append(safe_error_text(error).lower())

        if isinstance(error, (TimeoutError, ConnectionError, OSError)):
            return True

        if httpx is not None and isinstance(error, (httpx.TimeoutException, httpx.TransportError)):
            return True

    if any(status in RETRYABLE_STATUS_CODES for status in status_codes):
        return True

    if any(400 <= status < 500 and status != 429 for status in status_codes):
        return False

    combined = " ".join(messages)
    if any(keyword in combined for keyword in NON_RETRYABLE_KEYWORDS):
        return False

    return any(keyword in combined for keyword in retryable_keywords)


def compute_retry_delay(
    exc: BaseException,
    attempt: int,
    *,
    base_delay: float,
) -> float:
    delay = max(0.0, base_delay * (2**attempt))
    retry_after = _extract_retry_after(exc)
    if retry_after is None:
        return delay
    return max(delay, min(MAX_RETRY_AFTER_SECONDS, retry_after))


async def emit_progress(
    on_progress: Callable[[str], Awaitable[None]] | None,
    chunk: str,
) -> None:
    if on_progress is None:
        return

    try:
        await on_progress(chunk)
    except asyncio.CancelledError:
        raise
    except ProgressCallbackError:
        raise  # preserve subclass (StreamInterruptedError)
    except Exception as exc:
        raise ProgressCallbackError("progress callback failed") from exc


async def emit_progress_reset(on_progress: Callable[[str], Awaitable[None]] | None) -> None:
    await emit_progress(on_progress, PROGRESS_RESET)
