from __future__ import annotations

from bao.agent.memory import ExperienceAppendRequest, ExperienceListRequest, MemoryChangeEvent
from tests._memory_workspace_api_testkit import build_store


def test_experience_workspace_api_supports_filter_mutate_and_promote() -> None:
    store = build_store()
    store.append_experience(
        ExperienceAppendRequest(
            task="Fix auth cache",
            outcome="success",
            lessons="Use the shared session cache instead of duplicating state.",
            quality=5,
            category="coding",
            keywords="auth, cache",
            reasoning_trace="matched existing session pattern",
        )
    )

    items = store.list_experience_items(ExperienceListRequest(query="auth", min_quality=4))

    assert len(items) == 1
    item = items[0]
    assert item["task"] == "Fix auth cache"
    assert item["keywords"] == "auth, cache"
    assert item["deprecated"] is False

    key = item["key"]
    assert store.set_experience_deprecated(key, True) is True
    deprecated = store.get_experience_item(key)
    assert deprecated is not None
    assert deprecated["deprecated"] is True

    promoted = store.promote_experience_to_memory(key, "project")
    assert promoted is not None
    assert "Fix auth cache" in promoted["content"]

    assert store.delete_experience(key) is True
    assert store.get_experience_item(key) is None


def test_memory_change_events_are_broadcast_per_storage_root() -> None:
    received: list[MemoryChangeEvent] = []
    listener_store = build_store()
    emitter_store = build_store()
    listener_store._storage_root = "/tmp/bao-memory-root"
    emitter_store._storage_root = "/tmp/bao-memory-root"

    listener_store.add_change_listener(received.append)
    emitter_store._emit_change(scope="long_term", operation="append_fact", category="project")
    listener_store.remove_change_listener(received.append)

    assert len(received) == 1
    assert received[0].scope == "long_term"
    assert received[0].category == "project"
