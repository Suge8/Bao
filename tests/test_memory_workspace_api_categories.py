from __future__ import annotations

from bao.agent.memory import MEMORY_CATEGORIES
from tests._memory_workspace_api_testkit import build_store


def test_list_memory_categories_returns_fixed_category_dtos() -> None:
    store = build_store(
        [
            {
                "key": "long_term_project_1",
                "type": "long_term",
                "category": "project",
                "content": "Keep auth flow simple",
                "updated_at": "2026-03-12T00:00:00",
            },
            {
                "key": "long_term_project_2",
                "type": "long_term",
                "category": "project",
                "content": "Reuse session manager",
                "updated_at": "2026-03-12T00:00:00",
            },
            {
                "key": "long_term_general_1",
                "type": "long_term",
                "category": "general",
                "content": "Prefer concise replies",
                "updated_at": "2026-03-11T00:00:00",
            },
        ]
    )

    items = store.list_memory_categories()

    assert [item["category"] for item in items] == list(MEMORY_CATEGORIES)
    project = next(item for item in items if item["category"] == "project")
    personal = next(item for item in items if item["category"] == "personal")
    assert project["char_count"] > 0
    assert project["line_count"] == 2
    assert project["fact_count"] == 2
    assert personal["is_empty"] is True
    assert personal["key"] == "long_term_personal"


def test_memory_category_mutations_roundtrip_through_dtos() -> None:
    store = build_store()

    saved = store.get_memory_category("project")
    assert saved is not None
    assert saved["is_empty"] is True

    appended = store.append_memory_category("project", "Remember the release checklist")
    assert appended is not None
    assert appended["category"] == "project"
    assert "release checklist" in appended["content"]

    store.write_long_term("Stable summary", "project")
    rewritten = store.get_memory_category("project")
    assert rewritten is not None
    assert rewritten["content"] == "Stable summary"

    cleared = store.clear_memory_category("project")
    assert cleared is not None
    assert cleared["content"] == ""
    assert cleared["is_empty"] is True


def test_write_long_term_stores_fact_rows_and_remember_dedupes() -> None:
    store = build_store()

    store.write_long_term("Fact A\nFact B\nFact A", "project")
    rows = store._tbl.rows

    assert [row["content"] for row in rows] == ["Fact A", "Fact B"]

    store.remember("Fact B\nFact C", "project")
    detail = store.get_memory_category("project")

    assert detail is not None
    assert detail["content"] == "Fact A\nFact B\nFact C"
    assert detail["fact_count"] == 3
    assert [fact["content"] for fact in detail["facts"]] == ["Fact A", "Fact B", "Fact C"]


def test_memory_fact_api_lists_and_deletes_fact_rows() -> None:
    store = build_store()

    store.write_long_term("Fact A\nFact B", "project")
    facts = store.list_memory_facts("project")

    assert [fact["content"] for fact in facts] == ["Fact A", "Fact B"]

    deleted = store.delete_memory_fact("project", str(facts[0]["key"]))
    assert deleted is not None
    assert [fact["content"] for fact in deleted["facts"]] == ["Fact B"]


def test_memory_fact_api_upserts_single_fact_rows() -> None:
    store = build_store()

    created = store.upsert_memory_fact("project", "Keep memory settings user friendly")
    assert created is not None
    assert [fact["content"] for fact in created["facts"]] == ["Keep memory settings user friendly"]

    key = str(created["facts"][0]["key"])
    updated = store.upsert_memory_fact("project", "Keep memory settings genuinely useful", key=key)

    assert updated is not None
    assert str(updated["facts"][0]["key"]) == key
    assert [fact["content"] for fact in updated["facts"]] == [
        "Keep memory settings genuinely useful"
    ]


def test_memory_fact_api_append_preserves_existing_fact_keys() -> None:
    store = build_store()

    created = store.upsert_memory_fact("project", "Fact A")
    assert created is not None
    first_key = str(created["facts"][0]["key"])

    appended = store.upsert_memory_fact("project", "Fact B")

    assert appended is not None
    assert [fact["content"] for fact in appended["facts"]] == ["Fact A", "Fact B"]
    assert str(appended["facts"][0]["key"]) == first_key
    assert str(appended["facts"][1]["key"]) != first_key


def test_memory_fact_delete_preserves_remaining_fact_metadata() -> None:
    store = build_store()

    store.write_long_term("Fact A\nFact B", "project")
    facts = store.list_memory_facts("project")
    first_key = str(facts[0]["key"])
    second_key = str(facts[1]["key"])
    for row in store._tbl.rows:
        if row.get("key") == second_key:
            row["hit_count"] = 3
            row["last_hit_at"] = "2026-03-13T12:00:00"

    deleted = store.delete_memory_fact("project", first_key)

    assert deleted is not None
    remaining = deleted["facts"]
    assert len(remaining) == 1
    assert str(remaining[0]["key"]) == second_key
    assert remaining[0]["hit_count"] == 3
    assert remaining[0]["last_hit_at"] == "2026-03-13T12:00:00"


def test_forget_rewrites_category_with_fresh_updated_at() -> None:
    store = build_store(
        [
            {
                "key": "long_term_project_1",
                "type": "long_term",
                "category": "project",
                "content": "Fact A",
                "updated_at": "2026-03-10T00:00:00",
            },
            {
                "key": "long_term_project_2",
                "type": "long_term",
                "category": "project",
                "content": "Fact B",
                "updated_at": "2026-03-11T00:00:00",
            },
        ]
    )

    result = store.forget("Fact B")
    detail = store.get_memory_category("project")

    assert "Removed 1 memory entries" in result
    assert detail is not None
    assert detail["content"] == "Fact A"
    assert detail["updated_at"] != "2026-03-10T00:00:00"
