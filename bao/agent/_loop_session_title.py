from __future__ import annotations

from typing import Any, Callable, Iterable


def find_title_messages(
    messages: list[dict[str, Any]],
    *,
    extract_text: Callable[[Any], str],
    greeting_words: Iterable[str],
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    user_message, user_index = _find_title_user_message(
        messages,
        extract_text=extract_text,
        greeting_words=set(greeting_words),
    )
    if user_message is None:
        return None, None
    return user_message, _find_following_assistant_message(
        messages,
        start_index=user_index,
        extract_text=extract_text,
    )


def _find_title_user_message(
    messages: list[dict[str, Any]],
    *,
    extract_text: Callable[[Any], str],
    greeting_words: set[str],
) -> tuple[dict[str, Any] | None, int]:
    for index, message in enumerate(messages):
        if message["role"] != "user":
            continue
        text = (
            extract_text(message.get("content", ""))
            .strip()
            .strip("!\uff01?\uff1f.\u3002~\uff5e")
            .lower()
        )
        if text and text not in greeting_words and len(text) >= 2:
            return message, index
    return None, -1


def _find_following_assistant_message(
    messages: list[dict[str, Any]],
    *,
    start_index: int,
    extract_text: Callable[[Any], str],
) -> dict[str, Any] | None:
    for message in messages[start_index + 1 :]:
        if message["role"] == "assistant" and extract_text(message.get("content", "")):
            return message
    return None


def build_title_prompt(*, user_content: str, assistant_content: str) -> str:
    return (
        "Generate a short conversation title. Rules:\n"
        "- Chinese: max 12 chars. English: max 6 words\n"
        "- No quotes, no periods, no prefixes like '\u5173\u4e8e...'\n"
        "- Match the user's language\n\n"
        f"User: {user_content}\n"
        f"Assistant: {assistant_content}\n\n"
        'Return JSON: {"title": "your title here"}'
    )


def fallback_title(content: Any, *, extract_text: Callable[[Any], str]) -> str:
    return extract_text(content).strip()[:20]


def normalize_generated_title(result: dict[str, Any] | None) -> str:
    if not result:
        return ""
    return (
        str(result.get("title", ""))
        .strip()
        .strip("\"''\u201c\u201d\u2018\u2019\u3002.!\uff01")
    )
