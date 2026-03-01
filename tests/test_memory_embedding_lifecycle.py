import threading
import time
from typing import cast

from bao.agent.memory import MemoryStore


def _matches_where(row: dict[str, object], where: str | None) -> bool:
    if not where:
        return True
    if " AND " in where:
        return all(_matches_where(row, part.strip()) for part in where.split(" AND "))
    if where == "type != '_init_'":
        return row.get("type") != "_init_"
    if where == "type = 'experience'":
        return row.get("type") == "experience"
    if where == "type = 'long_term'":
        return row.get("type") == "long_term"
    if where.startswith("key = '") and where.endswith("'"):
        key = where[len("key = '") : -1]
        return row.get("key") == key
    if where == "type NOT IN ('experience', 'long_term')":
        return row.get("type") not in {"experience", "long_term"}
    return True


class _FakeSearch:
    def __init__(self, rows: list[dict[str, object]]):
        self._rows = rows
        self._where: str | None = None
        self._limit: int | None = None

    def where(self, expr: str):
        self._where = expr
        return self

    def limit(self, n: int):
        self._limit = n
        return self

    def to_list(self) -> list[dict[str, object]]:
        rows = [r for r in self._rows if _matches_where(r, self._where)]
        if self._limit is not None:
            rows = rows[: self._limit]
        return [dict(r) for r in rows]


class _FakeTable:
    def __init__(self, rows: list[dict[str, object]] | None = None):
        self.rows = [dict(r) for r in (rows or [])]

    def search(self, *_args, **_kwargs):
        return _FakeSearch(self.rows)

    def add(self, rows: list[dict[str, object]]):
        for row in rows:
            self.rows.append(dict(row))

    def delete(self, where: str):
        self.rows = [r for r in self.rows if not _matches_where(r, where)]


class _FakeDB:
    def __init__(self):
        self.tables: dict[str, _FakeTable] = {}

    def create_table(self, name: str, data: list[dict[str, object]]):
        tbl = _FakeTable(data)
        self.tables[name] = tbl
        return tbl

    def open_table(self, name: str):
        return self.tables[name]

    def drop_table(self, name: str):
        if name not in self.tables:
            raise KeyError(name)
        del self.tables[name]


class _FakeEmbed:
    def __init__(self):
        self.calls: list[str] = []

    def compute_source_embeddings(self, texts: list[str]):
        self.calls.extend(texts)
        return [[0.1, 0.2, 0.3] for _ in texts]


class _FlakyEmbed:
    def __init__(self):
        self.query_calls = 0

    def compute_query_embeddings(self, _query: str):
        self.query_calls += 1
        if self.query_calls == 1:
            raise TimeoutError("temporary timeout")
        return [[0.9, 0.1]]


def _build_store() -> MemoryStore:
    store = MemoryStore.__new__(MemoryStore)
    store._store_lock = threading.RLock()
    store._embed_timeout_s = 1
    store._embed_retry_attempts = 2
    store._embed_retry_backoff_ms = 0
    return store


def test_enrich_for_rerank_filters_stale_vector_rows():
    store = _build_store()
    fake_tbl = _FakeTable(
        [
            {"key": "k1", "content": "hello", "type": "history", "quality": 3},
        ]
    )
    setattr(store, "_tbl", fake_tbl)

    vec_rows = [
        {"key": "k1", "content": "hello", "type": "history", "_distance": 0.1},
        {"key": "k_stale", "content": "gone", "type": "history", "_distance": 0.2},
    ]

    enriched = store._enrich_for_rerank(vec_rows)

    assert len(enriched) == 1
    assert enriched[0]["key"] == "k1"
    assert "_distance" in enriched[0]


def test_backfill_embeddings_adds_missing_and_keeps_unmanaged_stale_keys():
    store = _build_store()
    embed = _FakeEmbed()
    fake_tbl = _FakeTable(
        [
            {"key": "k1", "content": "alpha", "type": "history"},
            {"key": "k2", "content": "beta", "type": "experience"},
        ]
    )
    fake_vec_tbl = _FakeTable(
        [
            {"key": "k2", "content": "beta", "type": "experience", "vector": [0.1, 0.2, 0.3]},
            {"key": "k_stale", "content": "stale", "type": "history", "vector": [0.1, 0.2, 0.3]},
        ]
    )
    setattr(store, "_embed_fn", cast(object, embed))
    setattr(store, "_tbl", fake_tbl)
    setattr(store, "_vec_tbl", cast(object, fake_vec_tbl))

    store._backfill_embeddings()

    keys = {r.get("key") for r in fake_vec_tbl.rows}
    assert keys == {"k1", "k2", "k_stale"}
    assert embed.calls == ["alpha"]


def test_backfill_embeddings_refreshes_changed_content_for_same_key():
    store = _build_store()
    embed = _FakeEmbed()
    fake_tbl = _FakeTable([{"key": "k2", "content": "beta-new", "type": "experience"}])
    fake_vec_tbl = _FakeTable(
        [
            {
                "key": "k2",
                "content": "beta-old",
                "type": "experience",
                "vector": [0.1, 0.2, 0.3],
            }
        ]
    )
    setattr(store, "_embed_fn", cast(object, embed))
    setattr(store, "_tbl", fake_tbl)
    setattr(store, "_vec_tbl", cast(object, fake_vec_tbl))

    store._backfill_embeddings()

    assert embed.calls == ["beta-new"]
    refreshed = [r for r in fake_vec_tbl.rows if r.get("key") == "k2"]
    assert len(refreshed) == 1
    assert refreshed[0]["content"] == "beta-new"


def test_query_embedding_retries_on_retryable_error():
    store = _build_store()
    embed = _FlakyEmbed()
    setattr(store, "_embed_fn", cast(object, embed))

    result = store._compute_query_embeddings("find this")

    assert result == [[0.9, 0.1]]
    assert embed.query_calls == 2


def test_run_with_timeout_uses_executor_timeout_path():
    started = time.time()

    def _slow() -> str:
        time.sleep(0.05)
        return "done"

    try:
        MemoryStore._run_with_timeout(0, _slow)
        assert False
    except TimeoutError as exc:
        assert "timed out" in str(exc)
        assert MemoryStore._is_retryable_embedding_error(exc)
    assert time.time() - started < 0.05


def test_migrate_schema_keeps_rows_beyond_10000_without_truncation():
    store = _build_store()
    fake_db = _FakeDB()
    fake_db.create_table("memory", [{"key": "legacy", "content": "x", "type": "history"}])
    fake_db.create_table(
        "memory_vectors",
        [{"key": "legacy", "content": "x", "type": "history", "vector": [0.1, 0.2]}],
    )
    setattr(store, "_db", fake_db)

    old_rows: list[dict[str, object]] = [
        {"key": f"h{i}", "content": f"c{i}", "type": "history", "updated_at": ""}
        for i in range(10050)
    ]
    old_tbl = _FakeTable(old_rows)

    migrated = store._migrate_schema(old_tbl)

    assert len(migrated.rows) == 10050
    migrated_keys = {r.get("key") for r in migrated.rows}
    assert "h0" in migrated_keys
    assert "h10049" in migrated_keys


def test_backfill_new_columns_keeps_rows_beyond_10000_without_truncation():
    store = _build_store()
    fake_db = _FakeDB()
    fake_db.create_table("memory", [{"key": "seed", "content": "x", "type": "history"}])
    setattr(store, "_db", fake_db)

    rows: list[dict[str, object]] = [
        {
            "key": f"k{i}",
            "content": f"c{i}",
            "type": "history",
            "category": "",
            "quality": 0,
            "uses": 0,
            "successes": 0,
            "outcome": "",
            "deprecated": False,
            "updated_at": "",
        }
        for i in range(10050)
    ]
    tbl = _FakeTable(rows)

    patched = store._backfill_new_columns(tbl)

    assert len(patched.rows) == 10050
    assert all("hit_count" in r for r in patched.rows)
    assert all("last_hit_at" in r for r in patched.rows)


def test_enrich_for_rerank_uses_key_lookup_beyond_500_rows():
    store = _build_store()
    rows: list[dict[str, object]] = [
        {"key": f"k{i}", "content": f"row-{i}", "type": "history", "quality": 3}
        for i in range(1200)
    ]
    setattr(store, "_tbl", _FakeTable(rows))

    vec_rows = [{"key": "k1100", "content": "stale", "type": "history", "_distance": 0.05}]
    enriched = store._enrich_for_rerank(vec_rows)

    assert len(enriched) == 1
    assert enriched[0]["key"] == "k1100"


def test_enrich_vector_results_uses_key_lookup_beyond_500_rows():
    store = _build_store()
    rows: list[dict[str, object]] = [
        {
            "key": f"e{i}",
            "content": f"Task: task-{i}\nLessons: l{i}",
            "type": "experience",
            "quality": 3,
            "uses": 0,
            "successes": 0,
            "outcome": "success",
            "deprecated": False,
            "updated_at": "",
            "category": "general",
        }
        for i in range(1300)
    ]
    setattr(store, "_tbl", _FakeTable(rows))

    vec_rows = [{"key": "e1250", "content": "outdated", "type": "experience", "_distance": 0.1}]
    enriched = store._enrich_vector_results(vec_rows)

    assert len(enriched) == 1
    assert enriched[0]["key"] == "e1250"
