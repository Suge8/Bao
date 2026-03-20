from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from ._manager_models import (
    DisplayTailSnapshot,
    Session,
    SessionChangeEvent,
    escape_sql_value,
    synchronized,
)


@dataclass
class SavePlan:
    session: Session
    safe: str
    meta_tbl: Any
    msg_tbl: Any | None
    prev_meta: list[dict[str, Any]]
    prev_msgs: list[dict[str, Any]]
    prev_tail: list[dict[str, Any]]
    metadata_json: str
    created_at: str
    updated_at: str
    metadata_changed: bool
    current_fingerprints: list[str]
    write_mode: str
    append_start: int
    projection_changed: bool
    display_tail: list[dict[str, Any]]
    messages_surface_changed: bool
    event_kind: str | None
    meta_written: bool = False
    tail_written: bool = False


@dataclass(frozen=True)
class PersistedMetaState:
    created_at: str
    updated_at: str
    metadata_json: str
    last_consolidated: int


class SessionManagerSaveMixin:
    @synchronized
    def save(self, session: Session, *, emit_change: bool = True) -> None:
        plan = self._prepare_save_plan(session)
        try:
            self._execute_save_plan(plan)
        except Exception:
            self._rollback_save_plan(plan)
            self._cache.pop(session.key, None)
            self._display_tail_cache.pop(session.key, None)
            raise
        self._finalize_save_plan(plan, emit_change=emit_change)

    def _prepare_save_plan(self, session: Session) -> SavePlan:
        safe = escape_sql_value(session.key)
        meta_tbl = self._meta_table()
        persisted_metadata, runtime_metadata = self._persisted_metadata_with_runtime(session)
        prev_meta, prev_msgs, prev_tail, msg_tbl = self._previous_save_rows(safe, need_msgs=False)
        prev_meta_row = prev_meta[0] if prev_meta else None
        next_meta = PersistedMetaState(
            created_at=session.created_at.isoformat(),
            updated_at=session.updated_at.isoformat(),
            metadata_json=json.dumps(persisted_metadata, ensure_ascii=False),
            last_consolidated=int(session.last_consolidated),
        )
        metadata_changed = self._save_metadata_changed(prev_meta_row, next_meta)
        current_fingerprints = self._message_fingerprints(session.messages)
        prev_fingerprints = self._resolve_previous_fingerprints(session, prev_meta, safe)
        write_mode = self._save_write_mode(current_fingerprints, prev_fingerprints, len(session.messages))
        append_start = len(prev_fingerprints)
        last_consolidated_changed = (
            prev_meta_row is None
            or int(prev_meta_row.get("last_consolidated", 0)) != next_meta.last_consolidated
        )
        projection_changed = prev_meta_row is None or write_mode != "noop" or last_consolidated_changed
        display_tail = self._display_tail_from_session(session) if projection_changed else []
        event_kind = "messages" if projection_changed else ("metadata" if metadata_changed else None)
        return SavePlan(
            session=session,
            safe=safe,
            meta_tbl=meta_tbl,
            msg_tbl=msg_tbl,
            prev_meta=prev_meta,
            prev_msgs=prev_msgs,
            prev_tail=prev_tail,
            metadata_json=next_meta.metadata_json,
            created_at=next_meta.created_at,
            updated_at=next_meta.updated_at,
            metadata_changed=metadata_changed,
            current_fingerprints=current_fingerprints,
            write_mode=write_mode,
            append_start=append_start,
            projection_changed=projection_changed,
            display_tail=display_tail,
            messages_surface_changed=projection_changed,
            event_kind=event_kind,
        )

    def _persisted_metadata_with_runtime(self, session: Session) -> tuple[dict[str, Any], Any]:
        from bao.session.state import nest_flat_persisted_metadata, split_runtime_metadata

        persisted_metadata, runtime_metadata = split_runtime_metadata(session.metadata)
        self._replace_runtime_metadata(session.key, runtime_metadata)
        session.metadata = self._merge_runtime_metadata(session.key, persisted_metadata)
        return nest_flat_persisted_metadata(persisted_metadata), runtime_metadata

    def _previous_save_rows(
        self,
        safe: str,
        *,
        need_msgs: bool,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], Any | None]:
        meta_tbl = self._meta_table()
        prev_meta: list[dict[str, Any]]
        try:
            prev_meta = meta_tbl.search().where(f"session_key = '{safe}'").limit(1).to_list()
        except Exception:
            prev_meta = []
        prev_msgs: list[dict[str, Any]] = []
        prev_tail: list[dict[str, Any]] = []
        msg_tbl = self._msg_table() if need_msgs else None
        return prev_meta, prev_msgs, prev_tail, msg_tbl

    @staticmethod
    def _save_metadata_changed(
        prev_meta_row: dict[str, Any] | None,
        next_meta: PersistedMetaState,
    ) -> bool:
        if prev_meta_row is None:
            return True
        return (
            str(prev_meta_row.get("created_at") or "") != next_meta.created_at
            or str(prev_meta_row.get("updated_at") or "") != next_meta.updated_at
            or str(prev_meta_row.get("metadata_json") or "{}") != next_meta.metadata_json
            or int(prev_meta_row.get("last_consolidated", 0)) != next_meta.last_consolidated
        )

    def _resolve_previous_fingerprints(
        self,
        session: Session,
        prev_meta: list[dict[str, Any]],
        safe: str,
    ) -> list[str]:
        prev_fingerprints = self._get_persisted_message_fingerprints(session)
        if prev_fingerprints is not None or not prev_meta:
            return prev_fingerprints or []
        prev_msgs = self._msg_table().search().where(f"session_key = '{safe}'").to_list()
        prev_msgs.sort(key=lambda row: int(row.get("idx", -1)))
        return [self._message_fingerprint_from_row(row) for row in prev_msgs]

    @staticmethod
    def _save_write_mode(current: list[str], previous: list[str], message_count: int) -> str:
        prev_count = len(previous)
        if current == previous:
            return "noop"
        if prev_count < message_count and current[:prev_count] == previous:
            return "append"
        if message_count == 0 and prev_count > 0:
            return "clear"
        return "rewrite"

    def _execute_save_plan(self, plan: SavePlan) -> None:
        if plan.metadata_changed:
            self._rewrite_meta_row(plan)
        self._write_message_rows(plan)
        if plan.projection_changed:
            self._write_tail_projection(plan)

    def _rewrite_meta_row(self, plan: SavePlan) -> None:
        plan.meta_tbl.delete(f"session_key = '{plan.safe}'")
        plan.meta_tbl.add([{
            "session_key": plan.session.key,
            "created_at": plan.created_at,
            "updated_at": plan.updated_at,
            "metadata_json": plan.metadata_json,
            "last_consolidated": plan.session.last_consolidated,
        }])
        plan.meta_written = True

    def _msg_table_for_plan(self, plan: SavePlan) -> Any:
        if plan.msg_tbl is None:
            plan.msg_tbl = self._msg_table()
        return plan.msg_tbl

    def _load_plan_prev_msgs(self, plan: SavePlan) -> list[dict[str, Any]]:
        if plan.prev_msgs:
            return plan.prev_msgs
        msg_tbl = self._msg_table_for_plan(plan)
        plan.prev_msgs = msg_tbl.search().where(f"session_key = '{plan.safe}'").to_list()
        plan.prev_msgs.sort(key=lambda row: int(row.get("idx", -1)))
        return plan.prev_msgs

    def _write_message_rows(self, plan: SavePlan) -> None:
        rows = [
            {"session_key": plan.session.key, "idx": idx, **self._message_storage_payload(msg)}
            for idx, msg in enumerate(plan.session.messages)
        ]
        if plan.write_mode == "append":
            append_rows = rows[plan.append_start :]
            if append_rows:
                self._msg_table_for_plan(plan).add(append_rows)
            return
        if plan.write_mode == "clear":
            if self._load_plan_prev_msgs(plan):
                self._msg_table_for_plan(plan).delete(f"session_key = '{plan.safe}'")
            return
        if plan.write_mode == "rewrite":
            self._load_plan_prev_msgs(plan)
            self._msg_table_for_plan(plan).delete(f"session_key = '{plan.safe}'")
            if rows:
                self._msg_table_for_plan(plan).add(rows)

    def _write_tail_projection(self, plan: SavePlan) -> None:
        tail_tbl = self._display_tail_table()
        try:
            plan.prev_tail = tail_tbl.search().where(f"session_key = '{plan.safe}'").limit(1).to_list()
        except Exception:
            plan.prev_tail = []
        self._write_display_tail_row(
            plan.session.key,
            DisplayTailSnapshot(
                updated_at=plan.updated_at,
                messages=plan.display_tail,
                message_count=len(plan.session.messages),
            ),
        )
        plan.tail_written = True

    def _rollback_save_plan(self, plan: SavePlan) -> None:
        if plan.meta_written:
            self._best_effort_delete(plan.meta_tbl, f"session_key = '{plan.safe}'")
        if plan.tail_written:
            self._best_effort_delete(self._display_tail_table(), f"session_key = '{plan.safe}'")
        if plan.msg_tbl is not None:
            if plan.write_mode == "append":
                expr = f"session_key = '{plan.safe}' AND idx >= {plan.append_start}"
                self._best_effort_delete(plan.msg_tbl, expr)
            elif plan.write_mode in {"clear", "rewrite"}:
                self._best_effort_delete(plan.msg_tbl, f"session_key = '{plan.safe}'")
        if plan.meta_written:
            self._best_effort_add(plan.meta_tbl, plan.prev_meta)
        if plan.tail_written:
            self._best_effort_add(self._display_tail_table(), plan.prev_tail)
        if plan.msg_tbl is not None and plan.write_mode in {"clear", "rewrite"}:
            self._best_effort_add(plan.msg_tbl, plan.prev_msgs)

    def _finalize_save_plan(self, plan: SavePlan, *, emit_change: bool) -> None:
        self._cache[plan.session.key] = plan.session
        self._set_persisted_message_fingerprints(plan.session, plan.current_fingerprints)
        if plan.messages_surface_changed:
            self._store_display_tail_cache(plan.session.key, plan.display_tail)
        if emit_change and plan.event_kind:
            self._emit_change(SessionChangeEvent(session_key=plan.session.key, kind=plan.event_kind))
