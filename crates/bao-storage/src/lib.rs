use chrono::{TimeZone, Utc};
use chrono_tz::Tz;
use cron::Schedule;
use rusqlite::{params, Connection, OptionalExtension};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use sha2::{Digest as _, Sha256};
use std::str::FromStr;
use std::sync::Mutex;
use thiserror::Error;

#[derive(Debug, Error)]
pub enum StorageError {
    #[error("sqlite: {0}")]
    Sqlite(#[from] rusqlite::Error),
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TaskRecord {
    pub id: String,
    pub title: String,
    pub enabled: bool,
    pub schedule_kind: String,
    pub run_at_ts: Option<i64>,
    pub interval_ms: Option<i64>,
    pub cron: Option<String>,
    pub timezone: Option<String>,
    pub next_run_at: Option<i64>,
    pub last_run_at: Option<i64>,
    pub last_status: Option<String>,
    pub last_error: Option<String>,
    pub tool_dimsum_id: String,
    pub tool_name: String,
    pub tool_args: Value,
    pub policy: Option<Value>,
    pub kill_switch_group: Option<String>,
    pub created_at: i64,
    pub updated_at: i64,
}

#[derive(Debug, Clone)]
pub struct MemoryItemRecord {
    pub memory_id: String,
    pub namespace: String,
    pub kind: String,
    pub title: String,
    pub content: Option<String>,
    pub json: Option<String>,
    pub score: f64,
    pub status: String,
    pub source_hash: Option<String>,
    pub created_at: i64,
    pub updated_at: i64,
    pub last_injected_at: Option<i64>,
    pub inject_count: i64,
}

#[derive(Debug, Clone, Serialize)]
pub struct MemoryVersionRecord {
    pub version_id: String,
    pub memory_id: String,
    pub prev_version_id: Option<String>,
    pub op: String,
    pub diff_json: String,
    pub actor: String,
    pub created_at: i64,
}

#[derive(Debug, Clone)]
pub struct MemoryLinkRecord {
    pub memory_id: String,
    pub kind: String,
    pub message_id: Option<String>,
    pub event_id: Option<i64>,
    pub artifact_sha256: Option<String>,
    pub weight: f64,
    pub note: Option<String>,
    pub created_at: i64,
}

pub struct Storage {
    sqlite_path: String,
    mutex: Mutex<()>,
}

impl Storage {
    pub fn new() -> Self {
        Self {
            sqlite_path: String::new(),
            mutex: Mutex::new(()),
        }
    }

    pub fn open(sqlite_path: String) -> Result<Self, StorageError> {
        Ok(Self {
            sqlite_path,
            mutex: Mutex::new(()),
        })
    }

    pub fn fetch_due_tasks(
        &self,
        now_ts: i64,
        limit: i64,
    ) -> Result<Vec<TaskRecord>, StorageError> {
        let _guard = self.mutex.lock().expect("storage mutex poisoned");
        let conn = Connection::open(&self.sqlite_path)?;
        let mut stmt = conn.prepare(
            "SELECT task_id, title, enabled, schedule_kind, run_at_ts, interval_ms, cron, timezone, next_run_at, last_run_at, last_status, last_error, tool_dimsum_id, tool_name, tool_args_json, policy_json, kill_switch_group, created_at, updated_at \
             FROM tasks \
             WHERE enabled=1 AND next_run_at IS NOT NULL AND next_run_at <= ?1 \
             ORDER BY next_run_at ASC LIMIT ?2",
        )?;
        let rows = stmt.query_map(params![now_ts, limit], |r| {
            let tool_args_json: String = r.get(14)?;
            let policy_json: Option<String> = r.get(15)?;
            Ok(TaskRecord {
                id: r.get(0)?,
                title: r.get(1)?,
                enabled: r.get::<_, i64>(2)? == 1,
                schedule_kind: r.get(3)?,
                run_at_ts: r.get(4)?,
                interval_ms: r.get(5)?,
                cron: r.get(6)?,
                timezone: r.get(7)?,
                next_run_at: r.get(8)?,
                last_run_at: r.get(9)?,
                last_status: r.get(10)?,
                last_error: r.get(11)?,
                tool_dimsum_id: r.get(12)?,
                tool_name: r.get(13)?,
                tool_args: serde_json::from_str::<Value>(&tool_args_json).unwrap_or(Value::Null),
                policy: policy_json.and_then(|s| serde_json::from_str::<Value>(&s).ok()),
                kill_switch_group: r.get(16)?,
                created_at: r.get(17)?,
                updated_at: r.get(18)?,
            })
        })?;

        let mut out = Vec::new();
        for row in rows {
            out.push(row?);
        }
        Ok(out)
    }

    pub fn mark_task_run(
        &self,
        task_id: &str,
        status: &str,
        error: Option<&str>,
        now_ts: i64,
    ) -> Result<(), StorageError> {
        let _guard = self.mutex.lock().expect("storage mutex poisoned");
        let conn = Connection::open(&self.sqlite_path)?;

        let (enabled, schedule_kind, interval_ms, cron, timezone): (i64, String, Option<i64>, Option<String>, Option<String>) = conn.query_row(
            "SELECT enabled, schedule_kind, interval_ms, cron, timezone FROM tasks WHERE task_id=?1",
            params![task_id],
            |r| Ok((r.get(0)?, r.get(1)?, r.get(2)?, r.get(3)?, r.get(4)?)),
        )?;

        let (enabled_after, next_run_at) = match schedule_kind.as_str() {
            "once" => (0_i64, None),
            _ => {
                let next = compute_repeating_next_run_at(
                    &schedule_kind,
                    interval_ms,
                    cron.as_deref(),
                    timezone.as_deref(),
                    now_ts,
                );
                (enabled, next)
            }
        };

        conn.execute(
            "UPDATE tasks SET last_run_at=?2, last_status=?3, last_error=?4, updated_at=?2, next_run_at=?5, enabled=?6 WHERE task_id=?1",
            params![task_id, now_ts, status, error, next_run_at, enabled_after],
        )?;
        Ok(())
    }

    pub fn insert_event(
        &self,
        ts: i64,
        ty: &str,
        session_id: Option<&str>,
        message_id: Option<&str>,
        device_id: Option<&str>,
        payload: &Value,
    ) -> Result<i64, StorageError> {
        let _guard = self.mutex.lock().expect("storage mutex poisoned");
        let conn = Connection::open(&self.sqlite_path)?;
        conn.pragma_update(None, "foreign_keys", "ON")?;
        let payload_json = serde_json::to_string(payload).unwrap_or_else(|_| "{}".to_string());
        conn.execute(
            "INSERT INTO events(ts, type, session_id, message_id, device_id, payload_json) VALUES (?1, ?2, ?3, ?4, ?5, ?6)",
            params![ts, ty, session_id, message_id, device_id, payload_json],
        )?;
        Ok(conn.last_insert_rowid())
    }

    pub fn insert_audit_event(
        &self,
        ts: i64,
        action: &str,
        subject_type: &str,
        subject_id: &str,
        payload: &Value,
    ) -> Result<(), StorageError> {
        let _guard = self.mutex.lock().expect("storage mutex poisoned");
        let conn = Connection::open(&self.sqlite_path)?;
        conn.pragma_update(None, "foreign_keys", "ON")?;

        let prev_hash: Option<String> = conn
            .query_row(
                "SELECT hash FROM audit_events ORDER BY id DESC LIMIT 1",
                [],
                |r| r.get(0),
            )
            .optional()?;

        let payload_json = serde_json::to_string(payload).unwrap_or_else(|_| "{}".to_string());
        let mut hasher = Sha256::new();
        hasher.update(prev_hash.clone().unwrap_or_default());
        hasher.update(action.as_bytes());
        hasher.update(subject_type.as_bytes());
        hasher.update(subject_id.as_bytes());
        hasher.update(payload_json.as_bytes());
        hasher.update(ts.to_string().as_bytes());
        let hash = hex::encode(hasher.finalize());

        conn.execute(
            "INSERT INTO audit_events(ts, action, subject_type, subject_id, payload_json, prev_hash, hash) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7)",
            params![ts, action, subject_type, subject_id, payload_json, prev_hash, hash],
        )?;
        Ok(())
    }

    pub fn get_task_by_id(&self, task_id: &str) -> Result<Option<TaskRecord>, StorageError> {
        let _guard = self.mutex.lock().expect("storage mutex poisoned");
        let conn = Connection::open(&self.sqlite_path)?;
        let mut stmt = conn.prepare(
            "SELECT task_id, title, enabled, schedule_kind, run_at_ts, interval_ms, cron, timezone, next_run_at, last_run_at, last_status, last_error, tool_dimsum_id, tool_name, tool_args_json, policy_json, kill_switch_group, created_at, updated_at FROM tasks WHERE task_id=?1",
        )?;
        let mut rows = stmt.query(params![task_id])?;
        if let Some(r) = rows.next()? {
            let tool_args_json: String = r.get(14)?;
            let policy_json: Option<String> = r.get(15)?;
            return Ok(Some(TaskRecord {
                id: r.get(0)?,
                title: r.get(1)?,
                enabled: r.get::<_, i64>(2)? == 1,
                schedule_kind: r.get(3)?,
                run_at_ts: r.get(4)?,
                interval_ms: r.get(5)?,
                cron: r.get(6)?,
                timezone: r.get(7)?,
                next_run_at: r.get(8)?,
                last_run_at: r.get(9)?,
                last_status: r.get(10)?,
                last_error: r.get(11)?,
                tool_dimsum_id: r.get(12)?,
                tool_name: r.get(13)?,
                tool_args: serde_json::from_str::<Value>(&tool_args_json).unwrap_or(Value::Null),
                policy: policy_json.and_then(|s| serde_json::from_str::<Value>(&s).ok()),
                kill_switch_group: r.get(16)?,
                created_at: r.get(17)?,
                updated_at: r.get(18)?,
            }));
        }
        Ok(None)
    }

    pub fn upsert_memory_item(&self, item: &MemoryItemRecord) -> Result<(), StorageError> {
        let _guard = self.mutex.lock().expect("storage mutex poisoned");
        let conn = Connection::open(&self.sqlite_path)?;
        conn.pragma_update(None, "foreign_keys", "ON")?;
        conn.execute(
            "INSERT INTO memory_items(memory_id, namespace, kind, title, content, json, score, status, source_hash, created_at, updated_at, last_injected_at, inject_count) \
             VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13) \
             ON CONFLICT(memory_id) DO UPDATE SET \
               namespace=excluded.namespace, kind=excluded.kind, title=excluded.title, content=excluded.content, json=excluded.json, score=excluded.score, status=excluded.status, source_hash=excluded.source_hash, updated_at=excluded.updated_at",
            params![
                item.memory_id,
                item.namespace,
                item.kind,
                item.title,
                item.content,
                item.json,
                item.score,
                item.status,
                item.source_hash,
                item.created_at,
                item.updated_at,
                item.last_injected_at,
                item.inject_count,
            ],
        )?;
        Ok(())
    }

    pub fn delete_memory_item(&self, memory_id: &str) -> Result<(), StorageError> {
        let _guard = self.mutex.lock().expect("storage mutex poisoned");
        let conn = Connection::open(&self.sqlite_path)?;
        conn.pragma_update(None, "foreign_keys", "ON")?;
        conn.execute(
            "DELETE FROM memory_items WHERE memory_id=?1",
            params![memory_id],
        )?;
        Ok(())
    }

    pub fn get_memory_item(
        &self,
        memory_id: &str,
    ) -> Result<Option<MemoryItemRecord>, StorageError> {
        let _guard = self.mutex.lock().expect("storage mutex poisoned");
        let conn = Connection::open(&self.sqlite_path)?;
        let mut stmt = conn.prepare(
            "SELECT memory_id, namespace, kind, title, content, json, score, status, source_hash, created_at, updated_at, last_injected_at, inject_count FROM memory_items WHERE memory_id=?1",
        )?;
        let mut rows = stmt.query(params![memory_id])?;
        if let Some(r) = rows.next()? {
            return Ok(Some(MemoryItemRecord {
                memory_id: r.get(0)?,
                namespace: r.get(1)?,
                kind: r.get(2)?,
                title: r.get(3)?,
                content: r.get(4)?,
                json: r.get(5)?,
                score: r.get(6)?,
                status: r.get(7)?,
                source_hash: r.get(8)?,
                created_at: r.get(9)?,
                updated_at: r.get(10)?,
                last_injected_at: r.get(11)?,
                inject_count: r.get(12)?,
            }));
        }
        Ok(None)
    }

    pub fn insert_memory_version(&self, version: &MemoryVersionRecord) -> Result<(), StorageError> {
        let _guard = self.mutex.lock().expect("storage mutex poisoned");
        let conn = Connection::open(&self.sqlite_path)?;
        conn.pragma_update(None, "foreign_keys", "ON")?;
        conn.execute(
            "INSERT INTO memory_versions(version_id, memory_id, prev_version_id, op, diff_json, actor, created_at) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7)",
            params![
                version.version_id,
                version.memory_id,
                version.prev_version_id,
                version.op,
                version.diff_json,
                version.actor,
                version.created_at,
            ],
        )?;
        Ok(())
    }

    pub fn insert_memory_link(&self, link: &MemoryLinkRecord) -> Result<(), StorageError> {
        let _guard = self.mutex.lock().expect("storage mutex poisoned");
        let conn = Connection::open(&self.sqlite_path)?;
        conn.pragma_update(None, "foreign_keys", "ON")?;
        conn.execute(
            "INSERT INTO memory_links(memory_id, kind, message_id, event_id, artifact_sha256, weight, note, created_at) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8)",
            params![
                link.memory_id,
                link.kind,
                link.message_id,
                link.event_id,
                link.artifact_sha256,
                link.weight,
                link.note,
                link.created_at,
            ],
        )?;
        Ok(())
    }

    pub fn list_memory_versions(
        &self,
        memory_id: &str,
    ) -> Result<Vec<MemoryVersionRecord>, StorageError> {
        let _guard = self.mutex.lock().expect("storage mutex poisoned");
        let conn = Connection::open(&self.sqlite_path)?;
        let mut stmt = conn.prepare(
            "SELECT version_id, memory_id, prev_version_id, op, diff_json, actor, created_at FROM memory_versions WHERE memory_id=?1 ORDER BY created_at DESC",
        )?;
        let rows = stmt.query_map(params![memory_id], |r| {
            Ok(MemoryVersionRecord {
                version_id: r.get(0)?,
                memory_id: r.get(1)?,
                prev_version_id: r.get(2)?,
                op: r.get(3)?,
                diff_json: r.get(4)?,
                actor: r.get(5)?,
                created_at: r.get(6)?,
            })
        })?;
        let mut out = Vec::new();
        for row in rows {
            out.push(row?);
        }
        Ok(out)
    }

    pub fn get_memory_version(
        &self,
        version_id: &str,
    ) -> Result<Option<MemoryVersionRecord>, StorageError> {
        let _guard = self.mutex.lock().expect("storage mutex poisoned");
        let conn = Connection::open(&self.sqlite_path)?;
        let mut stmt = conn.prepare(
            "SELECT version_id, memory_id, prev_version_id, op, diff_json, actor, created_at FROM memory_versions WHERE version_id=?1",
        )?;
        let mut rows = stmt.query(params![version_id])?;
        if let Some(r) = rows.next()? {
            return Ok(Some(MemoryVersionRecord {
                version_id: r.get(0)?,
                memory_id: r.get(1)?,
                prev_version_id: r.get(2)?,
                op: r.get(3)?,
                diff_json: r.get(4)?,
                actor: r.get(5)?,
                created_at: r.get(6)?,
            }));
        }
        Ok(None)
    }
}

pub fn compute_task_next_run_at(
    schedule_kind: &str,
    run_at_ts: Option<i64>,
    interval_ms: Option<i64>,
    cron_expr: Option<&str>,
    timezone: Option<&str>,
    now_ts: i64,
) -> Option<i64> {
    match schedule_kind {
        "once" => Some(run_at_ts.unwrap_or(now_ts)),
        "interval" | "cron" => {
            compute_repeating_next_run_at(schedule_kind, interval_ms, cron_expr, timezone, now_ts)
        }
        _ => None,
    }
}

fn compute_repeating_next_run_at(
    schedule_kind: &str,
    interval_ms: Option<i64>,
    cron_expr: Option<&str>,
    timezone: Option<&str>,
    now_ts: i64,
) -> Option<i64> {
    match schedule_kind {
        "interval" => interval_ms.map(|ms| {
            let secs = (ms / 1000).max(1);
            now_ts + secs
        }),
        "cron" => {
            let expr = cron_expr?;
            let schedule = Schedule::from_str(expr).ok()?;
            let next = if let Some(tz) = timezone.and_then(|s| s.parse::<Tz>().ok()) {
                let base = tz.timestamp_opt(now_ts, 0).single()?;
                schedule.after(&base).next().map(|dt| dt.timestamp())
            } else {
                let base = Utc.timestamp_opt(now_ts, 0).single()?;
                schedule.after(&base).next().map(|dt| dt.timestamp())
            };
            next.and_then(|ts| if ts <= now_ts { None } else { Some(ts) })
        }
        _ => None,
    }
}
