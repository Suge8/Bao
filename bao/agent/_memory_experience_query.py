from __future__ import annotations

from typing import Any, Protocol

from bao.agent._memory_experience_models import ExperienceListRequest


class _ExperienceQueryHost(Protocol):
    def _tokenize(self, text: str) -> list[str]: ...

    def should_skip_retrieval(self, query: str) -> bool: ...


def filter_experience_items(
    host: _ExperienceQueryHost,
    items: list[dict[str, Any]],
    request: ExperienceListRequest,
) -> list[dict[str, Any]]:
    filtered = items
    if request.query and not host.should_skip_retrieval(request.query):
        filtered = _filter_experience_query(host, filtered, request.query)
    if request.category:
        filtered = [item for item in filtered if item.get("category") == request.category]
    if request.outcome:
        filtered = [item for item in filtered if item.get("outcome") == request.outcome]
    if request.deprecated is not None:
        filtered = [item for item in filtered if bool(item.get("deprecated")) is request.deprecated]
    if request.min_quality > 0:
        filtered = [item for item in filtered if int(item.get("quality", 0)) >= request.min_quality]
    return filtered


def sort_experience_items(items: list[dict[str, Any]], sort_by: str) -> None:
    if sort_by == "quality_desc":
        items.sort(
            key=lambda item: (
                int(item.get("quality", 0)),
                int(item.get("uses", 0)),
                str(item.get("updated_at", "")),
            ),
            reverse=True,
        )
        return
    if sort_by == "uses_desc":
        items.sort(
            key=lambda item: (
                int(item.get("uses", 0)),
                int(item.get("successes", 0)),
                str(item.get("updated_at", "")),
            ),
            reverse=True,
        )
        return
    items.sort(key=lambda item: str(item.get("updated_at", "")), reverse=True)


def _filter_experience_query(
    host: _ExperienceQueryHost,
    items: list[dict[str, Any]],
    query: str,
) -> list[dict[str, Any]]:
    query_tokens = set(host._tokenize(query))
    if not query_tokens:
        return items
    return [item for item in items if query_tokens & _experience_item_tokens(host, item)]


def _experience_item_tokens(
    host: _ExperienceQueryHost,
    item: dict[str, Any],
) -> set[str]:
    return set(
        host._tokenize(
            " ".join(
                [
                    str(item.get("task", "")),
                    str(item.get("lessons", "")),
                    str(item.get("keywords", "")),
                    str(item.get("category", "")),
                    str(item.get("outcome", "")),
                ]
            )
        )
    )
