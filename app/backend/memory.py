from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, ClassVar

from PySide6.QtCore import Property, QObject, Signal, Slot

from app.backend.asyncio_runner import AsyncioRunner
from bao.agent.memory import MEMORY_CATEGORIES, MemoryChangeEvent, MemoryStore


def _parse_updated_at(value: Any) -> datetime | None:
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _format_updated_label(value: Any) -> str:
    dt = _parse_updated_at(value)
    if dt is None:
        return ""
    now = datetime.now(tz=dt.tzinfo)
    delta = now - dt
    seconds = max(0, int(delta.total_seconds()))
    if seconds < 60:
        return "<1m"
    if seconds < 3600:
        return f"{seconds // 60}m"
    if seconds < 86400:
        return f"{seconds // 3600}h"
    if seconds < 604800:
        return f"{seconds // 86400}d"
    if dt.year == now.year:
        return f"{dt.month}/{dt.day}"
    return f"{dt.year}/{dt.month}/{dt.day}"


class MemoryService(QObject):
    readyChanged: ClassVar[Signal] = Signal()
    busyChanged: ClassVar[Signal] = Signal()
    blockingBusyChanged: ClassVar[Signal] = Signal()
    errorChanged: ClassVar[Signal] = Signal(str)
    memoryCategoriesChanged: ClassVar[Signal] = Signal()
    experienceItemsChanged: ClassVar[Signal] = Signal()
    selectedMemoryCategoryChanged: ClassVar[Signal] = Signal()
    selectedMemoryFactChanged: ClassVar[Signal] = Signal()
    selectedMemoryFactKeyChanged: ClassVar[Signal] = Signal()
    selectedExperienceChanged: ClassVar[Signal] = Signal()
    memoryStatsChanged: ClassVar[Signal] = Signal()
    experienceStatsChanged: ClassVar[Signal] = Signal()
    operationFinished: ClassVar[Signal] = Signal(str, bool)
    _runnerResult: ClassVar[Signal] = Signal(str, bool, bool, str, object)
    _externalChangeRequested: ClassVar[Signal] = Signal(str, str, str)
    _MUTATION_BUSY_MESSAGE = "Another memory operation is already in progress."

    def __init__(self, runner: AsyncioRunner, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._runner = runner
        self._store: MemoryStore | None = None
        self._storage_root = ""
        self._ready = False
        self._busy = False
        self._busy_count = 0
        self._blocking_busy = False
        self._blocking_busy_count = 0
        self._error = ""
        self._memory_categories: list[dict[str, Any]] = []
        self._experience_items: list[dict[str, Any]] = []
        self._selected_memory_category: dict[str, Any] = {}
        self._selected_memory_fact: dict[str, Any] = {}
        self._selected_memory_fact_key = ""
        self._selected_experience: dict[str, Any] = {}
        self._memory_stats: dict[str, Any] = {}
        self._experience_stats: dict[str, Any] = {}
        self._selected_memory_category_name = "project"
        self._selected_experience_key = ""
        self._experience_query = ""
        self._experience_category = ""
        self._experience_outcome = ""
        self._experience_deprecated_mode = "active"
        self._experience_min_quality = 0
        self._experience_sort_by = "updated_desc"
        self._experience_request_seq = 0
        self._latest_experience_request_seq = 0
        self._experience_detail_request_seq = 0
        self._latest_experience_detail_request_seq = 0
        self._store_listener = self._on_store_change
        self._runnerResult.connect(self._handle_runner_result)
        self._externalChangeRequested.connect(self._handle_external_change)

    @Property(bool, notify=readyChanged)
    def ready(self) -> bool:
        return self._ready

    @Property(bool, notify=busyChanged)
    def busy(self) -> bool:
        return self._busy

    @Property(bool, notify=blockingBusyChanged)
    def blockingBusy(self) -> bool:
        return self._blocking_busy

    @Property(str, notify=errorChanged)
    def lastError(self) -> str:
        return self._error

    @Property(list, notify=memoryCategoriesChanged)
    def memoryCategories(self) -> list[dict[str, Any]]:
        return [dict(item) for item in self._memory_categories]

    @Property(list, notify=experienceItemsChanged)
    def experienceItems(self) -> list[dict[str, Any]]:
        return [dict(item) for item in self._experience_items]

    @Property(dict, notify=selectedMemoryCategoryChanged)
    def selectedMemoryCategory(self) -> dict[str, Any]:
        return dict(self._selected_memory_category)

    @Property(dict, notify=selectedMemoryFactChanged)
    def selectedMemoryFact(self) -> dict[str, Any]:
        return dict(self._selected_memory_fact)

    @Property(str, notify=selectedMemoryFactKeyChanged)
    def selectedMemoryFactKey(self) -> str:
        return self._selected_memory_fact_key

    @Property(dict, notify=selectedExperienceChanged)
    def selectedExperience(self) -> dict[str, Any]:
        return dict(self._selected_experience)

    @Property(dict, notify=memoryStatsChanged)
    def memoryStats(self) -> dict[str, Any]:
        return dict(self._memory_stats)

    @Property(dict, notify=experienceStatsChanged)
    def experienceStats(self) -> dict[str, Any]:
        return dict(self._experience_stats)

    @Slot(str)
    def bootstrapWorkspace(self, workspace_path: str) -> None:
        self.bootstrapStorageRoot(workspace_path)

    @Slot(str)
    def bootstrapStorageRoot(self, storage_root: str) -> None:
        raw_path = storage_root.strip()
        if not raw_path:
            return
        if raw_path == self._storage_root and self._store is not None:
            self.refreshAll()
            return
        self._storage_root = raw_path
        self._submit_task("bootstrap", self._bootstrap_store(raw_path))

    @Slot()
    def refreshAll(self) -> None:
        self.refreshMemoryCategories()
        self.reloadExperiences(
            self._experience_query,
            self._experience_category,
            self._experience_outcome,
            self._experience_deprecated_mode,
            self._experience_min_quality,
            self._experience_sort_by,
        )

    @Slot()
    def refreshMemoryCategories(self) -> None:
        self._submit_task("load_memory", self._load_memory_categories())

    @Slot(str)
    def selectMemoryCategory(self, category: str) -> None:
        normalized = category if category in MEMORY_CATEGORIES else "project"
        self._apply_selected_memory_category(normalized, self._memory_category_from_cache(normalized))

    @Slot(str)
    def selectMemoryFact(self, key: str) -> None:
        normalized = key.strip()
        if not normalized:
            self._apply_selected_memory_fact({})
            return
        selected = self._memory_fact_by_key(self._selected_memory_category, normalized)
        if selected:
            self._apply_selected_memory_fact(selected)

    @Slot(str, str)
    def saveMemoryCategory(self, category: str, content: str) -> None:
        self._submit_task("save_memory", self._save_memory_category(category, content))

    @Slot(str, str)
    def appendMemoryCategory(self, category: str, content: str) -> None:
        self._submit_task("append_memory", self._append_memory_category(category, content))

    @Slot(str)
    def clearMemoryCategory(self, category: str) -> None:
        self._submit_task("clear_memory", self._clear_memory_category(category))

    @Slot(str, str, str)
    def saveMemoryFact(self, category: str, key: str, content: str) -> None:
        self._submit_task("save_memory_fact", self._save_memory_fact(category, key, content))

    @Slot(str, str)
    def deleteMemoryFact(self, category: str, key: str) -> None:
        self._submit_task("delete_memory_fact", self._delete_memory_fact(category, key))

    @Slot(str, str, str, str, int, str)
    def reloadExperiences(
        self,
        query: str = "",
        category: str = "",
        outcome: str = "",
        deprecated_mode: str = "active",
        min_quality: int = 0,
        sort_by: str = "updated_desc",
    ) -> None:
        self._experience_query = query.strip()
        self._experience_category = category.strip()
        self._experience_outcome = outcome.strip()
        self._experience_deprecated_mode = (
            deprecated_mode if deprecated_mode in {"active", "all", "deprecated"} else "active"
        )
        self._experience_min_quality = max(0, int(min_quality))
        self._experience_sort_by = (
            sort_by if sort_by in {"updated_desc", "quality_desc", "uses_desc"} else "updated_desc"
        )
        self._experience_request_seq += 1
        seq = self._experience_request_seq
        self._latest_experience_request_seq = seq
        self._submit_task("load_experiences", self._load_experiences(seq))

    @Slot(str)
    def selectExperience(self, key: str) -> None:
        normalized = key.strip()
        if not normalized:
            self._selected_experience_key = ""
            self._selected_experience = {}
            self.selectedExperienceChanged.emit()
            return
        self._selected_experience_key = normalized
        cached = self._experience_from_cache(normalized)
        if cached is not None:
            self._selected_experience = cached
            self.selectedExperienceChanged.emit()
        self._experience_detail_request_seq += 1
        seq = self._experience_detail_request_seq
        self._latest_experience_detail_request_seq = seq
        self._submit_task("load_experience_detail", self._load_experience_detail(normalized, seq))

    @Slot(str, bool)
    def setExperienceDeprecated(self, key: str, deprecated: bool) -> None:
        self._submit_task("deprecate_experience", self._set_experience_deprecated(key, deprecated))

    @Slot(str)
    def deleteExperience(self, key: str) -> None:
        self._submit_task("delete_experience", self._delete_experience(key))

    @Slot(str, str)
    def promoteExperienceToMemory(self, key: str, category: str) -> None:
        self._submit_task("promote_experience", self._promote_experience_to_memory(key, category))

    @Slot()
    def shutdown(self) -> None:
        if self._store is not None:
            try:
                self._detach_store_listener(self._store)
                self._store.close()
            except Exception:
                pass
        self._store = None
        self._ready = False
        self.readyChanged.emit()

    def _submit_task(self, kind: str, coro: Coroutine[Any, Any, Any]) -> None:
        blocking = self._is_blocking_kind(kind)
        if blocking and self._blocking_busy:
            coro.close()
            self.operationFinished.emit(self._MUTATION_BUSY_MESSAGE, False)
            return
        future = self._submit_safe(coro)
        if future is None:
            return
        self._set_busy(True)
        if blocking:
            self._set_blocking_busy(True)
        future.add_done_callback(
            lambda f, task_kind=kind, task_blocking=blocking: self._emit_runner_result(
                task_kind, task_blocking, f
            )
        )

    def _submit_safe(self, coro: Coroutine[Any, Any, Any]) -> Any:
        try:
            return self._runner.submit(coro)
        except RuntimeError:
            coro.close()
            self._set_error("Asyncio runner is not available.")
            return None

    async def _run_user_io(self, fn: Any, *args: Any, **kwargs: Any) -> Any:
        if isinstance(self._runner, AsyncioRunner):
            return await self._runner.run_user_io(fn, *args, **kwargs)
        return await asyncio.to_thread(fn, *args, **kwargs)

    async def _bootstrap_store(self, storage_root: str) -> dict[str, Any]:
        root = Path(storage_root).expanduser()
        await self._run_user_io(lambda: root.mkdir(parents=True, exist_ok=True))
        store = await self._run_user_io(MemoryStore, root)
        memory_items = await self._run_user_io(store.list_memory_categories)
        experience_items = await self._run_user_io(store.list_experience_items)
        return {
            "store": store,
            "memory_items": memory_items,
            "experience_items": experience_items,
            "memory_category": self._selected_memory_category_name,
            "experience_key": self._selected_experience_key,
        }

    async def _load_memory_categories(self) -> dict[str, Any]:
        store = self._require_store()
        items = await self._run_user_io(store.list_memory_categories)
        return {"memory_items": items, "memory_category": self._selected_memory_category_name}

    async def _save_memory_category(self, category: str, content: str) -> dict[str, Any]:
        store = self._require_store()
        await self._run_user_io(store.write_long_term, content, category)
        items = await self._run_user_io(store.list_memory_categories)
        detail = await self._run_user_io(store.get_memory_category, category)
        return {"memory_items": items, "memory_category": category, "memory_detail": detail}

    async def _append_memory_category(self, category: str, content: str) -> dict[str, Any]:
        store = self._require_store()
        detail = await self._run_user_io(store.append_memory_category, category, content)
        items = await self._run_user_io(store.list_memory_categories)
        return {"memory_items": items, "memory_category": category, "memory_detail": detail}

    async def _clear_memory_category(self, category: str) -> dict[str, Any]:
        store = self._require_store()
        detail = await self._run_user_io(store.clear_memory_category, category)
        items = await self._run_user_io(store.list_memory_categories)
        return {"memory_items": items, "memory_category": category, "memory_detail": detail}

    async def _save_memory_fact(self, category: str, key: str, content: str) -> dict[str, Any]:
        store = self._require_store()
        detail = await self._run_user_io(store.upsert_memory_fact, category, content, key=key)
        if detail is None:
            raise RuntimeError("Failed to save memory fact")
        items = await self._run_user_io(store.list_memory_categories)
        facts = detail.get("facts") if isinstance(detail, dict) else None
        saved_key = key.strip()
        if not saved_key and isinstance(facts, list) and facts:
            saved_key = str(facts[-1].get("key", ""))
        return {
            "memory_items": items,
            "memory_category": category,
            "memory_detail": detail,
            "memory_fact_key": saved_key,
        }

    async def _delete_memory_fact(self, category: str, key: str) -> dict[str, Any]:
        store = self._require_store()
        detail = await self._run_user_io(store.delete_memory_fact, category, key)
        if detail is None:
            raise RuntimeError("Failed to delete memory fact")
        items = await self._run_user_io(store.list_memory_categories)
        return {"memory_items": items, "memory_category": category, "memory_detail": detail}

    async def _load_experiences(self, seq: int) -> dict[str, Any]:
        store = self._require_store()
        items = await self._load_filtered_experience_items(store)
        detail = None
        if self._selected_experience_key:
            detail = await self._run_user_io(
                store.get_experience_item, self._selected_experience_key
            )
        return {"seq": seq, "experience_items": items, "experience_detail": detail}

    async def _load_experience_detail(self, key: str, seq: int) -> dict[str, Any]:
        store = self._require_store()
        detail = await self._run_user_io(store.get_experience_item, key)
        return {"experience_detail": detail, "detail_seq": seq}

    async def _set_experience_deprecated(self, key: str, deprecated: bool) -> dict[str, Any]:
        store = self._require_store()
        ok = await self._run_user_io(store.set_experience_deprecated, key, deprecated)
        if not ok:
            raise RuntimeError("Failed to update experience state")
        items = await self._load_filtered_experience_items(store)
        detail = await self._run_user_io(store.get_experience_item, key)
        return {"experience_items": items, "experience_detail": detail}

    async def _delete_experience(self, key: str) -> dict[str, Any]:
        store = self._require_store()
        ok = await self._run_user_io(store.delete_experience, key)
        if not ok:
            raise RuntimeError("Failed to delete experience")
        items = await self._load_filtered_experience_items(store)
        return {"experience_items": items, "experience_detail": None, "deleted_key": key}

    async def _promote_experience_to_memory(self, key: str, category: str) -> dict[str, Any]:
        store = self._require_store()
        detail = await self._run_user_io(store.promote_experience_to_memory, key, category)
        if detail is None:
            raise RuntimeError("Failed to promote experience")
        items = await self._run_user_io(store.list_memory_categories)
        return {"memory_items": items, "memory_category": category, "memory_detail": detail}

    @staticmethod
    def _is_blocking_kind(kind: str) -> bool:
        return kind in {
            "bootstrap",
            "save_memory",
            "append_memory",
            "clear_memory",
            "save_memory_fact",
            "delete_memory_fact",
            "deprecate_experience",
            "delete_experience",
            "promote_experience",
        }

    def _current_experience_deprecated_filter(self) -> bool | None:
        if self._experience_deprecated_mode == "deprecated":
            return True
        if self._experience_deprecated_mode == "active":
            return False
        return None

    async def _load_filtered_experience_items(self, store: MemoryStore) -> list[dict[str, Any]]:
        return await self._run_user_io(
            lambda: store.list_experience_items(
                self._experience_query,
                category=self._experience_category,
                outcome=self._experience_outcome,
                deprecated=self._current_experience_deprecated_filter(),
                min_quality=self._experience_min_quality,
                sort_by=self._experience_sort_by,
            )
        )

    def _emit_runner_result(self, kind: str, blocking: bool, future: Any) -> None:
        if future.cancelled():
            self._runnerResult.emit(kind, blocking, False, "Cancelled", None)
            return
        error = future.exception()
        if error is not None:
            self._runnerResult.emit(kind, blocking, False, str(error), None)
            return
        self._runnerResult.emit(kind, blocking, True, "", future.result())

    def _handle_runner_result(
        self, kind: str, blocking: bool, ok: bool, error: str, payload: object
    ) -> None:
        self._set_busy(False)
        if blocking:
            self._set_blocking_busy(False)
        if not ok:
            self._set_error(error)
            self.operationFinished.emit(error, False)
            return

        self._set_error("")
        data = payload if isinstance(payload, dict) else {}
        if kind == "bootstrap":
            previous = self._store
            store = data.get("store")
            self._store = store if isinstance(store, MemoryStore) else self._store
            if previous is not None and previous is not self._store:
                self._detach_store_listener(previous)
            if isinstance(self._store, MemoryStore) and self._store is not previous:
                self._attach_store_listener(self._store)
            if previous is not None and previous is not self._store:
                try:
                    previous.close()
                except Exception:
                    pass
        if kind == "load_experiences":
            seq = int(data.get("seq", 0) or 0)
            if seq < self._latest_experience_request_seq:
                return
        if kind == "load_experience_detail":
            detail_seq = int(data.get("detail_seq", 0) or 0)
            if detail_seq < self._latest_experience_detail_request_seq:
                return
        if "memory_items" in data:
            self._apply_memory_items(data.get("memory_items"))
        if "experience_items" in data:
            self._apply_experience_items(data.get("experience_items"))
        if "memory_category" in data:
            category = str(data.get("memory_category") or self._selected_memory_category_name)
            detail = data.get("memory_detail")
            preferred_fact_key = str(data.get("memory_fact_key") or "")
            self._apply_selected_memory_category(category, detail, preferred_fact_key)
        if kind == "load_memory" and not self._selected_memory_category:
            self._apply_selected_memory_category(
                self._selected_memory_category_name,
                self._memory_category_from_cache(self._selected_memory_category_name)
                or self._memory_category_from_cache("project"),
            )
        if "experience_detail" in data:
            detail = data.get("experience_detail")
            if isinstance(detail, dict):
                self._selected_experience = self._decorate_experience_item(detail)
                self._selected_experience_key = str(self._selected_experience.get("key", ""))
            elif detail is None and kind == "delete_experience":
                self._selected_experience = {}
                self._selected_experience_key = ""
            elif self._selected_experience_key:
                self._selected_experience = (
                    self._experience_from_cache(self._selected_experience_key) or {}
                )
            else:
                self._selected_experience = {}
            self.selectedExperienceChanged.emit()
        if kind == "load_experiences" and not self._selected_experience and self._experience_items:
            self._selected_experience = dict(self._experience_items[0])
            self._selected_experience_key = str(self._selected_experience.get("key", ""))
            self.selectedExperienceChanged.emit()
        if kind == "bootstrap":
            self._ready = True
            self.readyChanged.emit()

        messages = {
            "save_memory": "Memory saved",
            "append_memory": "Memory updated",
            "clear_memory": "Memory cleared",
            "save_memory_fact": "Memory fact saved",
            "delete_memory_fact": "Memory fact deleted",
            "deprecate_experience": "Experience updated",
            "delete_experience": "Experience deleted",
            "promote_experience": "Experience promoted",
        }
        if kind in messages:
            self.operationFinished.emit(messages[kind], True)

    def _require_store(self) -> MemoryStore:
        if self._store is None:
            raise RuntimeError("Memory workspace is not ready")
        return self._store

    def _set_busy(self, busy: bool) -> None:
        if busy:
            self._busy_count += 1
        else:
            self._busy_count = max(0, self._busy_count - 1)
        normalized = self._busy_count > 0
        if normalized == self._busy:
            return
        self._busy = normalized
        self.busyChanged.emit()

    def _set_blocking_busy(self, busy: bool) -> None:
        if busy:
            self._blocking_busy_count += 1
        else:
            self._blocking_busy_count = max(0, self._blocking_busy_count - 1)
        normalized = self._blocking_busy_count > 0
        if normalized == self._blocking_busy:
            return
        self._blocking_busy = normalized
        self.blockingBusyChanged.emit()

    def _set_error(self, error: str) -> None:
        if error == self._error:
            return
        self._error = error
        self.errorChanged.emit(error)

    def _attach_store_listener(self, store: MemoryStore) -> None:
        add_listener = getattr(store, "add_change_listener", None)
        if callable(add_listener):
            add_listener(self._store_listener)

    def _detach_store_listener(self, store: MemoryStore) -> None:
        remove_listener = getattr(store, "remove_change_listener", None)
        if callable(remove_listener):
            remove_listener(self._store_listener)

    def _on_store_change(self, event: MemoryChangeEvent) -> None:
        self._externalChangeRequested.emit(event.scope, event.category, event.operation)

    def _handle_external_change(self, scope: str, category: str, operation: str) -> None:
        if self._store is None or not self._ready:
            return
        if scope == "experience":
            self.reloadExperiences(
                self._experience_query,
                self._experience_category,
                self._experience_outcome,
                self._experience_deprecated_mode,
                self._experience_min_quality,
                self._experience_sort_by,
            )
            if operation == "promote":
                self.refreshMemoryCategories()
            return
        if scope == "long_term":
            self.refreshMemoryCategories()

    def _decorate_memory_item(self, item: dict[str, Any]) -> dict[str, Any]:
        decorated = dict(item)
        decorated["updated_label"] = _format_updated_label(item.get("updated_at"))
        facts = item.get("facts")
        if isinstance(facts, list):
            decorated["facts"] = [
                {
                    **dict(fact),
                    "updated_label": _format_updated_label(
                        fact.get("last_hit_at") or fact.get("updated_at")
                    ),
                }
                for fact in facts
                if isinstance(fact, dict)
            ]
        return decorated

    def _decorate_experience_item(self, item: dict[str, Any]) -> dict[str, Any]:
        decorated = dict(item)
        uses = int(item.get("uses", 0) or 0)
        successes = int(item.get("successes", 0) or 0)
        decorated["updated_label"] = _format_updated_label(item.get("updated_at"))
        decorated["last_hit_label"] = _format_updated_label(item.get("last_hit_at"))
        decorated["success_rate"] = round((successes / uses) * 100, 1) if uses > 0 else 0.0
        return decorated

    def _apply_memory_items(self, items: object) -> None:
        normalized = (
            [self._decorate_memory_item(item) for item in items] if isinstance(items, list) else []
        )
        self._memory_categories = [item for item in normalized if isinstance(item, dict)]
        self._memory_stats = self._build_memory_stats(self._memory_categories)
        self.memoryCategoriesChanged.emit()
        self.memoryStatsChanged.emit()

    def _apply_experience_items(self, items: object) -> None:
        normalized = (
            [self._decorate_experience_item(item) for item in items]
            if isinstance(items, list)
            else []
        )
        self._experience_items = [item for item in normalized if isinstance(item, dict)]
        self._experience_stats = self._build_experience_stats(self._experience_items)
        self.experienceItemsChanged.emit()
        self.experienceStatsChanged.emit()

    def _memory_category_from_cache(self, category: str) -> dict[str, Any] | None:
        for item in self._memory_categories:
            if str(item.get("category", "")) == category:
                return dict(item)
        return None

    def _memory_fact_by_key(
        self,
        detail: dict[str, Any],
        key: str,
    ) -> dict[str, Any]:
        normalized = key.strip()
        if not normalized:
            return {}
        facts = detail.get("facts")
        if not isinstance(facts, list):
            return {}
        for fact in facts:
            if not isinstance(fact, dict):
                continue
            if str(fact.get("key", "")) == normalized:
                return dict(fact)
        return {}

    def _resolve_selected_memory_fact(
        self,
        detail: dict[str, Any],
        preferred_key: str = "",
    ) -> dict[str, Any]:
        selected = self._memory_fact_by_key(detail, preferred_key)
        if selected:
            return selected
        facts = detail.get("facts")
        if not isinstance(facts, list) or not facts:
            return {}
        first = facts[0]
        return dict(first) if isinstance(first, dict) else {}

    def _apply_selected_memory_fact(self, fact: object) -> None:
        selected = dict(fact) if isinstance(fact, dict) else {}
        next_fact_key = str(selected.get("key", "")).strip()
        fact_changed = selected != self._selected_memory_fact
        key_changed = next_fact_key != self._selected_memory_fact_key
        self._selected_memory_fact = selected
        self._selected_memory_fact_key = next_fact_key
        if fact_changed:
            self.selectedMemoryFactChanged.emit()
        if key_changed:
            self.selectedMemoryFactKeyChanged.emit()

    def _apply_selected_memory_category(
        self,
        category: str,
        detail: object,
        preferred_fact_key: str = "",
    ) -> None:
        normalized_category = category if category in MEMORY_CATEGORIES else "project"
        if isinstance(detail, dict):
            selected = self._decorate_memory_item(detail)
        else:
            selected = self._memory_category_from_cache(normalized_category) or {}
        selected_fact = self._resolve_selected_memory_fact(
            selected,
            preferred_fact_key or self._selected_memory_fact_key,
        )
        category_changed = selected != self._selected_memory_category
        fact_changed = selected_fact != self._selected_memory_fact
        next_fact_key = str(selected_fact.get("key", "")).strip()
        key_changed = next_fact_key != self._selected_memory_fact_key
        self._selected_memory_category_name = normalized_category
        self._selected_memory_category = selected
        self._selected_memory_fact = selected_fact
        self._selected_memory_fact_key = next_fact_key
        if category_changed:
            self.selectedMemoryCategoryChanged.emit()
        if fact_changed:
            self.selectedMemoryFactChanged.emit()
        if key_changed:
            self.selectedMemoryFactKeyChanged.emit()

    def _experience_from_cache(self, key: str) -> dict[str, Any] | None:
        for item in self._experience_items:
            if str(item.get("key", "")) == key:
                return dict(item)
        return None

    @staticmethod
    def _build_memory_stats(items: list[dict[str, Any]]) -> dict[str, Any]:
        used = [item for item in items if not bool(item.get("is_empty", False))]
        latest = max((str(item.get("updated_at", "")) for item in used), default="")
        return {
            "used_categories": len(used),
            "total_categories": len(MEMORY_CATEGORIES),
            "total_chars": sum(int(item.get("char_count", 0) or 0) for item in items),
            "total_facts": sum(int(item.get("fact_count", 0) or 0) for item in items),
            "latest_updated_at": latest,
            "latest_updated_label": _format_updated_label(latest),
        }

    @staticmethod
    def _build_experience_stats(items: list[dict[str, Any]]) -> dict[str, Any]:
        recent_count = 0
        for item in items:
            dt = _parse_updated_at(item.get("updated_at"))
            if dt is None:
                continue
            recent_cutoff = datetime.now(tz=dt.tzinfo) - timedelta(days=7)
            if dt >= recent_cutoff:
                recent_count += 1
        return {
            "total_count": len(items),
            "active_count": sum(1 for item in items if not bool(item.get("deprecated", False))),
            "deprecated_count": sum(1 for item in items if bool(item.get("deprecated", False))),
            "high_quality_count": sum(1 for item in items if int(item.get("quality", 0) or 0) >= 4),
            "recent_count": recent_count,
        }
