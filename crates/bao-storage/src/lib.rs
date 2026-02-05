use chrono::{TimeZone, Utc};
use chrono_tz::Tz;
use cron::Schedule;
use rusqlite::{params, Connection};
use serde::{Deserialize, Serialize};
use serde_json::Value;
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

    pub fn fetch_due_tasks(&self, now_ts: i64, limit: i64) -> Result<Vec<TaskRecord>, StorageError> {
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

    pub fn mark_task_run(&self, task_id: &str, status: &str, error: Option<&str>, now_ts: i64) -> Result<(), StorageError> {
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
                let next = compute_next_run_at(
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
}

fn compute_next_run_at(
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
            if let Some(tz) = timezone.and_then(|s| s.parse::<Tz>().ok()) {
                let base = tz.timestamp_opt(now_ts, 0).single()?;
                schedule.after(&base).next().map(|dt| dt.timestamp())
            } else {
                let base = Utc.timestamp_opt(now_ts, 0).single()?;
                schedule.after(&base).next().map(|dt| dt.timestamp())
            }
        }
        _ => None,
    }
}
