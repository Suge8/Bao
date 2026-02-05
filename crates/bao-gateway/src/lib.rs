use std::{
    collections::HashMap,
    net::{IpAddr, Ipv4Addr, SocketAddr},
    sync::{Arc, Mutex},
    time::{Duration, SystemTime, UNIX_EPOCH},
};

use bao_api::{BaoEventV1, MemoryHitV1, MemoryMutationPlanV1, TaskSpecV1};
use base64::{engine::general_purpose, Engine as _};
use rand::{rngs::OsRng, RngCore};
use rusqlite::{params, Connection};
use serde::Deserialize;
use serde_json::Value;
use sha1::{Digest as _, Sha1};
use thiserror::Error;
use tokio::{
    io::{AsyncReadExt, AsyncWriteExt},
    net::{TcpListener, TcpStream},
    time,
};

// -----------------------------
// Public config + handle
// -----------------------------

#[derive(Debug, Clone)]
pub struct GatewayConfig {
    /// Bind address.
    /// - default: 127.0.0.1
    /// - allow LAN: 0.0.0.0
    pub bind_addr: IpAddr,
    pub port: u16,
}

impl Default for GatewayConfig {
    fn default() -> Self {
        Self {
            bind_addr: IpAddr::V4(Ipv4Addr::LOCALHOST),
            port: 3901,
        }
    }
}

#[derive(Clone)]
pub struct GatewayHandle {
    state: Arc<GatewayState>,
}

impl GatewayHandle {
    /// Expose underlying SQLite path for desktop glue.
    pub fn sqlite_path(&self) -> String {
        self.state.sqlite_path.clone()
    }

    pub fn create_pairing_token(&self) -> String {
        self.state.auth.create_pairing()
    }

    pub fn revoke_pairing_token(&self, token: &str) {
        self.state.auth.revoke(token)
    }

    /// Runtime config update from desktop IPC.
    ///
    /// NOTE: phase1 minimal: this only affects *next* start() bind; we don't hot-rebind.
    pub fn set_allow_lan(&self, allow: bool) {
        let mut cfg = self.state.runtime_cfg.lock().expect("cfg mutex poisoned");
        cfg.allow_lan = allow;
    }

    // -----------------------------
    // Desktop IPC helpers (phase1 minimal)
    // -----------------------------

    pub async fn send_message(&self, session_id: String, text: String) -> Result<BaoEventV1, GatewayError> {
        let sid = session_id.clone();
        let payload = serde_json::json!({"sessionId": session_id, "text": text});
        append_and_load_event(&self.state, now_ts(), "message.send", Some(sid.as_str()), None, None, &payload).await
    }

    pub async fn list_sessions(&self) -> Result<BaoEventV1, GatewayError> {
        let sessions = query_sessions(&self.state.sqlite_path).await?;
        let payload = serde_json::json!({"sessions": sessions});
        append_and_load_event(&self.state, now_ts(), "sessions.list", None, None, None, &payload).await
    }

    pub async fn list_tasks(&self) -> Result<BaoEventV1, GatewayError> {
        let tasks = query_tasks(&self.state.sqlite_path).await?;
        let payload = serde_json::json!({"tasks": tasks});
        append_and_load_event(&self.state, now_ts(), "tasks.list", None, None, None, &payload).await
    }

    pub async fn create_task(&self, spec: TaskSpecV1) -> Result<BaoEventV1, GatewayError> {
        let ts = now_ts();
        tokio::task::spawn_blocking({
            let sqlite_path = self.state.sqlite_path.clone();
            let spec = spec.clone();
            move || {
                let conn = Connection::open(sqlite_path)?;
                conn.pragma_update(None, "foreign_keys", "ON")?;

                let schedule_kind = match spec.schedule.kind {
                    bao_api::TaskScheduleKindV1::Once => "once",
                    bao_api::TaskScheduleKindV1::Interval => "interval",
                    bao_api::TaskScheduleKindV1::Cron => "cron",
                };

                let tool = spec.action.toolCall;
                let tool_args_json = serde_json::to_string(&tool.args).unwrap_or_else(|_| "null".to_string());

                let policy_json = spec.policy.as_ref().and_then(|p| serde_json::to_string(p).ok());
                let kill_switch_group = spec.policy.as_ref().and_then(|p| p.killSwitchGroup.clone());

                conn.execute(
                    "INSERT INTO tasks(task_id, title, enabled, schedule_kind, run_at_ts, interval_ms, cron, timezone, next_run_at, last_run_at, last_status, last_error, tool_dimsum_id, tool_name, tool_args_json, policy_json, kill_switch_group, created_at, updated_at) \
                     VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, NULL, NULL, NULL, ?10, ?11, ?12, ?13, ?14, ?15, ?15) \
                     ON CONFLICT(task_id) DO UPDATE SET \
                       title=excluded.title, enabled=excluded.enabled, schedule_kind=excluded.schedule_kind, \
                       run_at_ts=excluded.run_at_ts, interval_ms=excluded.interval_ms, cron=excluded.cron, timezone=excluded.timezone, \
                       next_run_at=excluded.next_run_at, tool_dimsum_id=excluded.tool_dimsum_id, tool_name=excluded.tool_name, \
                       tool_args_json=excluded.tool_args_json, policy_json=excluded.policy_json, kill_switch_group=excluded.kill_switch_group, \
                       updated_at=excluded.updated_at",
                    params![
                        spec.id,
                        spec.title,
                        if spec.enabled { 1i64 } else { 0i64 },
                        schedule_kind,
                        spec.schedule.runAtTs,
                        spec.schedule.intervalMs,
                        spec.schedule.cron,
                        spec.schedule.timezone,
                        spec.schedule.runAtTs,
                        tool.dimsumId,
                        tool.toolName,
                        tool_args_json,
                        policy_json,
                        kill_switch_group,
                        ts,
                    ],
                )?;

                Ok::<_, GatewayError>(())
            }
        })
        .await
        .map_err(|e| GatewayError::Protocol(format!("join: {e}")))??;

        let payload = serde_json::to_value(&spec).unwrap_or(Value::Null);
        append_and_load_event(&self.state, ts, "tasks.create", None, None, None, &payload).await
    }

    pub async fn update_task(&self, spec: TaskSpecV1) -> Result<BaoEventV1, GatewayError> {
        let ts = now_ts();
        tokio::task::spawn_blocking({
            let sqlite_path = self.state.sqlite_path.clone();
            let spec = spec.clone();
            move || {
                let conn = Connection::open(sqlite_path)?;
                conn.pragma_update(None, "foreign_keys", "ON")?;

                let schedule_kind = match spec.schedule.kind {
                    bao_api::TaskScheduleKindV1::Once => "once",
                    bao_api::TaskScheduleKindV1::Interval => "interval",
                    bao_api::TaskScheduleKindV1::Cron => "cron",
                };

                let tool = spec.action.toolCall;
                let tool_args_json = serde_json::to_string(&tool.args).unwrap_or_else(|_| "null".to_string());

                let policy_json = spec.policy.as_ref().and_then(|p| serde_json::to_string(p).ok());
                let kill_switch_group = spec.policy.as_ref().and_then(|p| p.killSwitchGroup.clone());

                conn.execute(
                    "UPDATE tasks SET title=?2, enabled=?3, schedule_kind=?4, run_at_ts=?5, interval_ms=?6, cron=?7, timezone=?8,\
                     next_run_at=?9, tool_dimsum_id=?10, tool_name=?11, tool_args_json=?12, policy_json=?13, kill_switch_group=?14,\
                     updated_at=?15 WHERE task_id=?1",
                    params![
                        spec.id,
                        spec.title,
                        if spec.enabled { 1i64 } else { 0i64 },
                        schedule_kind,
                        spec.schedule.runAtTs,
                        spec.schedule.intervalMs,
                        spec.schedule.cron,
                        spec.schedule.timezone,
                        spec.schedule.runAtTs,
                        tool.dimsumId,
                        tool.toolName,
                        tool_args_json,
                        policy_json,
                        kill_switch_group,
                        ts,
                    ],
                )?;

                Ok::<_, GatewayError>(())
            }
        })
        .await
        .map_err(|e| GatewayError::Protocol(format!("join: {e}")))??;

        let payload = serde_json::to_value(&spec).unwrap_or(Value::Null);
        append_and_load_event(&self.state, ts, "tasks.update", None, None, None, &payload).await
    }

    pub async fn enable_task(&self, task_id: String) -> Result<BaoEventV1, GatewayError> {
        let ts = now_ts();
        tokio::task::spawn_blocking({
            let sqlite_path = self.state.sqlite_path.clone();
            let task_id = task_id.clone();
            move || {
                let conn = Connection::open(sqlite_path)?;
                conn.pragma_update(None, "foreign_keys", "ON")?;
                conn.execute(
                    "UPDATE tasks SET enabled=1, updated_at=?2 WHERE task_id=?1",
                    params![task_id, ts],
                )?;
                Ok::<_, GatewayError>(())
            }
        })
        .await
        .map_err(|e| GatewayError::Protocol(format!("join: {e}")))??;

        let payload = serde_json::json!({"taskId": task_id, "enabled": true});
        append_and_load_event(&self.state, ts, "tasks.enable", None, None, None, &payload).await
    }

    pub async fn disable_task(&self, task_id: String) -> Result<BaoEventV1, GatewayError> {
        let ts = now_ts();
        tokio::task::spawn_blocking({
            let sqlite_path = self.state.sqlite_path.clone();
            let task_id = task_id.clone();
            move || {
                let conn = Connection::open(sqlite_path)?;
                conn.pragma_update(None, "foreign_keys", "ON")?;
                conn.execute(
                    "UPDATE tasks SET enabled=0, updated_at=?2 WHERE task_id=?1",
                    params![task_id, ts],
                )?;
                Ok::<_, GatewayError>(())
            }
        })
        .await
        .map_err(|e| GatewayError::Protocol(format!("join: {e}")))??;

        let payload = serde_json::json!({"taskId": task_id, "enabled": false});
        append_and_load_event(&self.state, ts, "tasks.disable", None, None, None, &payload).await
    }

    pub async fn run_task_now(&self, task_id: String) -> Result<BaoEventV1, GatewayError> {
        // Phase1: scheduler/runner wiring will execute tool calls; this just emits an intent event.
        let ts = now_ts();
        let payload = serde_json::json!({"taskId": task_id});
        append_and_load_event(&self.state, ts, "tasks.runNow", None, None, None, &payload).await
    }

    pub async fn search_index(&self, query: String, limit: i64) -> Result<BaoEventV1, GatewayError> {
        let hits = memory_search_index(&self.state.sqlite_path, &query, limit).await?;
        let payload = serde_json::json!({"query": query, "hits": hits});
        append_and_load_event(&self.state, now_ts(), "memory.searchIndex", None, None, None, &payload).await
    }

    pub async fn get_items(&self, ids: Vec<String>) -> Result<BaoEventV1, GatewayError> {
        let items = memory_get_items(&self.state.sqlite_path, &ids).await?;
        let payload = serde_json::json!({"ids": ids, "items": items});
        append_and_load_event(&self.state, now_ts(), "memory.getItems", None, None, None, &payload).await
    }

    pub async fn get_timeline(&self, namespace: Option<String>) -> Result<BaoEventV1, GatewayError> {
        let timeline = memory_get_timeline(&self.state.sqlite_path, namespace.clone()).await?;
        let payload = serde_json::json!({"namespace": namespace, "timeline": timeline});
        append_and_load_event(&self.state, now_ts(), "memory.getTimeline", None, None, None, &payload).await
    }

    pub async fn apply_mutation_plan(&self, _plan: MemoryMutationPlanV1) -> Result<BaoEventV1, GatewayError> {
        // Phase1 minimal: store-side implementation lands with memory engine.
        let payload = serde_json::json!({"ok": true});
        append_and_load_event(&self.state, now_ts(), "memory.applyMutationPlan", None, None, None, &payload).await
    }

    pub async fn rollback_version(&self, memory_id: String, version_id: String) -> Result<BaoEventV1, GatewayError> {
        let payload = serde_json::json!({"memoryId": memory_id, "versionId": version_id});
        append_and_load_event(&self.state, now_ts(), "memory.rollbackVersion", None, None, None, &payload).await
    }

    pub async fn list_dimsums(&self) -> Result<BaoEventV1, GatewayError> {
        let dimsums = query_dimsums(&self.state.sqlite_path).await?;
        let payload = serde_json::json!({"dimsums": dimsums});
        append_and_load_event(&self.state, now_ts(), "dimsums.list", None, None, None, &payload).await
    }

    pub async fn list_memories(&self) -> Result<BaoEventV1, GatewayError> {
        let memories = query_memories(&self.state.sqlite_path).await?;
        let payload = serde_json::json!({"memories": memories});
        append_and_load_event(&self.state, now_ts(), "memories.list", None, None, None, &payload).await
    }

    pub async fn get_settings(&self) -> Result<BaoEventV1, GatewayError> {
        let settings = query_settings(&self.state.sqlite_path).await?;
        let payload = serde_json::json!({"settings": settings});
        append_and_load_event(&self.state, now_ts(), "settings.get", None, None, None, &payload).await
    }

    /// Upsert a single setting key.
    ///
    /// Phase1: writes to `settings` table and emits a `settings.update` event.
    pub async fn update_setting(&self, key: String, value: Value) -> Result<BaoEventV1, GatewayError> {
        let ts = now_ts();
        tokio::task::spawn_blocking({
            let sqlite_path = self.state.sqlite_path.clone();
            let key = key.clone();
            let value_json = serde_json::to_string(&value).unwrap_or_else(|_| "null".to_string());
            move || {
                let conn = Connection::open(sqlite_path)?;
                conn.pragma_update(None, "foreign_keys", "ON")?;
                conn.execute(
                    "INSERT INTO settings(key, value_json, updated_at) VALUES (?1, ?2, ?3) \
                     ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json, updated_at=excluded.updated_at",
                    params![key, value_json, ts],
                )?;
                Ok::<_, GatewayError>(())
            }
        })
        .await
        .map_err(|e| GatewayError::Protocol(format!("join: {e}")))??;

        let payload = serde_json::json!({"key": key, "value": value});
        append_and_load_event(&self.state, ts, "settings.update", None, None, None, &payload).await
    }

    pub async fn events_since(&self, last_event_id: Option<i64>, limit: i64) -> Result<Vec<BaoEventV1>, GatewayError> {
        let out = tokio::task::spawn_blocking({
            let sqlite_path = self.state.sqlite_path.clone();
            move || load_events_since(&sqlite_path, last_event_id, limit)
        })
        .await
        .map_err(|e| GatewayError::Protocol(format!("join: {e}")))??;
        Ok(out)
    }
}

async fn memory_search_index(sqlite_path: &str, query: &str, limit: i64) -> Result<Vec<MemoryHitV1>, GatewayError> {
    let q = query.to_string();
    let p = sqlite_path.to_string();
    let limit = limit.clamp(1, 200) as usize;
    tokio::task::spawn_blocking(move || {
        let conn = rusqlite::Connection::open(p)?;
        conn.pragma_update(None, "foreign_keys", "ON")?;

        let mut out = Vec::with_capacity(limit);
        let mut stmt = conn.prepare(
            "SELECT memory_id, namespace, kind, title, COALESCE(content, ''), score, status, updated_at \
             FROM memory_items \
             WHERE (?1 = '' OR rowid IN (SELECT rowid FROM memory_fts WHERE memory_fts MATCH ?1)) \
             ORDER BY updated_at DESC \
             LIMIT ?2",
        )?;
        let rows = stmt.query_map(params![q, limit as i64], |r| {
            let content: String = r.get(4)?;
            Ok(MemoryHitV1 {
                id: r.get(0)?,
                namespace: r.get(1)?,
                kind: r.get(2)?,
                title: r.get(3)?,
                snippet: content.chars().take(120).collect::<String>(),
                score: r.get::<_, f64>(5)?,
                tags: vec![],
                status: r.get::<_, Option<String>>(6)?,
                updatedAt: r.get::<_, Option<i64>>(7)?,
                evidenceCount: None,
            })
        })?;

        for r in rows {
            out.push(r?);
        }
        Ok::<_, GatewayError>(out)
    })
    .await
    .map_err(|e| GatewayError::Protocol(format!("join: {e}")))?
}

async fn memory_get_items(sqlite_path: &str, ids: &[String]) -> Result<Vec<Value>, GatewayError> {
    let p = sqlite_path.to_string();
    let ids = ids.to_vec();
    tokio::task::spawn_blocking(move || {
        let conn = rusqlite::Connection::open(p)?;
        conn.pragma_update(None, "foreign_keys", "ON")?;

        if ids.is_empty() {
            return Ok::<_, GatewayError>(Vec::new());
        }

        let mut out = Vec::with_capacity(ids.len());
        let mut stmt = conn.prepare(
            "SELECT memory_id, namespace, kind, title, content, json, score, status, source_hash, created_at, updated_at \
             FROM memory_items WHERE memory_id = ?1",
        )?;
        for id in ids {
            let rows = stmt.query_map(params![id], |r| {
                let json_text: Option<String> = r.get(5)?;
                Ok(serde_json::json!({
                    "id": r.get::<_, String>(0)?,
                    "namespace": r.get::<_, String>(1)?,
                    "kind": r.get::<_, String>(2)?,
                    "title": r.get::<_, String>(3)?,
                    "content": r.get::<_, Option<String>>(4)?,
                    "json": json_text.and_then(|s| serde_json::from_str::<Value>(&s).ok()),
                    "score": r.get::<_, Option<f64>>(6)?,
                    "status": r.get::<_, Option<String>>(7)?,
                    "sourceHash": r.get::<_, Option<String>>(8)?,
                    "createdAt": r.get::<_, i64>(9)?,
                    "updatedAt": r.get::<_, i64>(10)?,
                }))
            })?;
            for row in rows {
                out.push(row?);
            }
        }
        Ok::<_, GatewayError>(out)
    })
    .await
    .map_err(|e| GatewayError::Protocol(format!("join: {e}")))?
}

async fn memory_get_timeline(sqlite_path: &str, namespace: Option<String>) -> Result<Vec<Value>, GatewayError> {
    let p = sqlite_path.to_string();
    tokio::task::spawn_blocking(move || {
        let conn = rusqlite::Connection::open(p)?;
        conn.pragma_update(None, "foreign_keys", "ON")?;

        let mut out = Vec::new();
        let mut stmt = conn.prepare(
            "SELECT namespace, COUNT(*), MAX(updated_at) \
             FROM memory_items \
             WHERE (?1 IS NULL OR namespace = ?1) \
             GROUP BY namespace \
             ORDER BY MAX(updated_at) DESC",
        )?;
        let rows = stmt.query_map(params![namespace], |r| {
            Ok(serde_json::json!({
                "namespace": r.get::<_, String>(0)?,
                "count": r.get::<_, i64>(1)?,
                "updatedAt": r.get::<_, Option<i64>>(2)?,
            }))
        })?;
        for row in rows {
            out.push(row?);
        }
        Ok::<_, GatewayError>(out)
    })
    .await
    .map_err(|e| GatewayError::Protocol(format!("join: {e}")))?
}

#[derive(Clone)]
pub struct GatewayServer {
    state: Arc<GatewayState>,
}

impl GatewayServer {
    /// Open gateway with a SQLite file path.
    ///
    /// Phase1: we keep gateway self-contained and run bao-storage's SQL migration in-process.
    pub fn open(sqlite_path: impl Into<String>) -> Result<(Self, GatewayHandle), GatewayError> {
        let sqlite_path = sqlite_path.into();
        init_sqlite(&sqlite_path)?;

        let state = Arc::new(GatewayState {
            sqlite_path,
            auth: AuthRegistry::new(),
            runtime_cfg: Mutex::new(RuntimeConfig { allow_lan: false }),
        });
        Ok((
            Self {
                state: state.clone(),
            },
            GatewayHandle { state },
        ))
    }

    pub async fn start(&self, mut cfg: GatewayConfig) -> Result<(), GatewayError> {
        // Apply allow_lan override.
        let allow_lan = self.state.runtime_cfg.lock().expect("cfg mutex poisoned").allow_lan;
        if allow_lan {
            cfg.bind_addr = IpAddr::V4(Ipv4Addr::UNSPECIFIED);
        } else {
            cfg.bind_addr = IpAddr::V4(Ipv4Addr::LOCALHOST);
        }

        let addr = SocketAddr::new(cfg.bind_addr, cfg.port);
        let listener = TcpListener::bind(addr).await?;
        self.start_with_listener(listener).await
    }

    /// Start gateway with an already-bound listener.
    ///
    /// Useful for tests (bind to port 0 then read `local_addr`).
    pub async fn start_with_listener(&self, listener: TcpListener) -> Result<(), GatewayError> {
        loop {
            let (stream, _) = listener.accept().await?;
            let state = self.state.clone();
            tokio::spawn(async move {
                let _ = handle_connection(state, stream).await;
            });
        }
    }

    // phase1: events are tailed from SQLite (events table).
}

#[derive(Debug, Clone)]
struct RuntimeConfig {
    allow_lan: bool,
}

#[derive(Debug)]
struct GatewayState {
    sqlite_path: String,
    auth: AuthRegistry,
    runtime_cfg: Mutex<RuntimeConfig>,
}

// -----------------------------
// Protocol (WS V1, minimal)
// -----------------------------

/// client->server (V1 fixed)
#[derive(Debug, Clone, Deserialize)]
#[serde(tag = "type")]
pub enum ClientFrameV1 {
    #[serde(rename = "hello")]
    Hello {
        token: String,
        #[serde(rename = "lastEventId")]
        #[serde(default)]
        last_event_id: Option<i64>,
    },

    #[serde(rename = "sendMessage")]
    SendMessage {
        #[serde(rename = "sessionId")]
        session_id: String,
        text: String,
    },

    #[serde(rename = "listSessions")]
    ListSessions,
    #[serde(rename = "listTasks")]
    ListTasks,
    #[serde(rename = "listDimsums")]
    ListDimsums,
    #[serde(rename = "listMemories")]
    ListMemories,
    #[serde(rename = "getSettings")]
    GetSettings,
}

// -----------------------------
// Pairing token registry
// -----------------------------

#[derive(Debug)]
struct AuthRegistry {
    /// One-time pairing tokens.
    pairing: Mutex<HashMap<String, bool>>,
    /// Long-lived device tokens (phase1: in-memory only).
    device: Mutex<HashMap<String, bool>>,
}

impl AuthRegistry {
    fn new() -> Self {
        Self {
            pairing: Mutex::new(HashMap::new()),
            device: Mutex::new(HashMap::new()),
        }
    }

    fn create_pairing(&self) -> String {
        let mut bytes = [0u8; 32];
        OsRng.fill_bytes(&mut bytes);
        let token = format!("p_{}", general_purpose::URL_SAFE_NO_PAD.encode(bytes));
        let mut g = self.pairing.lock().expect("pairing mutex poisoned");
        g.insert(token.clone(), false);
        token
    }

    fn revoke(&self, token: &str) {
        {
            let mut g = self.pairing.lock().expect("pairing mutex poisoned");
            if let Some(v) = g.get_mut(token) {
                *v = true;
                return;
            }
        }
        {
            let mut g = self.device.lock().expect("device mutex poisoned");
            if let Some(v) = g.get_mut(token) {
                *v = true;
            }
        }
    }

    fn accept_or_pair(&self, token: &str) -> AuthDecision {
        // Phase1 rule: token kind is explicit.
        // - p_* : one-time pairing token, returns a minted device token (d_*)
        // - d_* : long-lived device token
        if token.starts_with("d_") {
            let g = self.device.lock().expect("device mutex poisoned");
            return match g.get(token).copied() {
                Some(false) => AuthDecision::Accepted { new_device_token: None },
                _ => AuthDecision::Rejected,
            };
        }

        if token.starts_with("p_") {
            let mut g = self.pairing.lock().expect("pairing mutex poisoned");
            return match g.get(token).copied() {
                Some(false) => {
                    g.remove(token);
                    let device_token = self.create_device_token();
                    let mut d = self.device.lock().expect("device mutex poisoned");
                    d.insert(device_token.clone(), false);
                    AuthDecision::Accepted {
                        new_device_token: Some(device_token),
                    }
                }
                _ => AuthDecision::Rejected,
            };
        }

        AuthDecision::Rejected
    }

    fn create_device_token(&self) -> String {
        let mut bytes = [0u8; 32];
        OsRng.fill_bytes(&mut bytes);
        format!("d_{}", general_purpose::URL_SAFE_NO_PAD.encode(bytes))
    }
}

enum AuthDecision {
    Accepted { new_device_token: Option<String> },
    Rejected,
}

// -----------------------------
// Storage queries (sessions/tasks/dimsums/memories/settings/events)
// -----------------------------

fn now_ts() -> i64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or(Duration::from_secs(0))
        .as_secs() as i64
}

fn load_events_since(sqlite_path: &str, last_event_id: Option<i64>, limit: i64) -> Result<Vec<BaoEventV1>, GatewayError> {
    let limit = limit.clamp(1, 5000);
    let from = last_event_id.unwrap_or(0);

    let conn = rusqlite::Connection::open(sqlite_path)?;
    conn.pragma_update(None, "foreign_keys", "ON")?;

    let mut stmt = conn.prepare(
        "SELECT eventId, ts, type, session_id, message_id, device_id, payload_json \
         FROM events WHERE eventId > ?1 ORDER BY eventId ASC LIMIT ?2",
    )?;
    let rows = stmt.query_map(params![from, limit], |r| {
        let event_id: i64 = r.get(0)?;
        let ts: i64 = r.get(1)?;
        let ty: String = r.get(2)?;
        let session_id: Option<String> = r.get(3)?;
        let message_id: Option<String> = r.get(4)?;
        let device_id: Option<String> = r.get(5)?;
        let payload_json: String = r.get(6)?;

        Ok(BaoEventV1 {
            eventId: event_id,
            ts,
            r#type: ty,
            sessionId: session_id,
            messageId: message_id,
            deviceId: device_id,
            payload: serde_json::from_str::<Value>(&payload_json).unwrap_or(Value::Null),
        })
    })?;

    let mut out = vec![];
    for r in rows {
        out.push(r?);
    }
    Ok(out)
}

fn init_sqlite(sqlite_path: &str) -> Result<(), GatewayError> {
    let conn = Connection::open(sqlite_path)?;
    conn.pragma_update(None, "foreign_keys", "ON")?;

    // Reuse bao-storage migration SQL verbatim.
    // NOTE: This is allowed because we only read from that file.
    const INIT_SQL: &str = include_str!("../../bao-storage/migrations/0001_init.sql");
    conn.execute_batch(INIT_SQL)?;
    Ok(())
}

// -----------------------------
// Minimal WebSocket-over-TCP implementation
// -----------------------------

// NOTE: This is a minimal, self-contained WS implementation sufficient for tests.
// - Text frames only
// - Client->server must be masked (RFC6455); we enforce and unmask
// - Server->client is unmasked
// - No fragmentation

async fn handle_connection(state: Arc<GatewayState>, mut stream: TcpStream) -> Result<(), GatewayError> {
    // 1) HTTP Upgrade handshake
    let req = read_http_request(&mut stream).await?;
    let (method, path) = parse_http_request_line(&req)
        .ok_or_else(|| GatewayError::Handshake("bad request line".to_string()))?;

    if method == "GET" && path == "/health" {
        return write_http_json(&mut stream, 200, serde_json::json!({"ok": true})).await;
    }
    if method == "GET" && path == "/device/info" {
        return write_http_json(
            &mut stream,
            200,
            serde_json::json!({"deviceId": "desktop", "platform": "desktop", "baoCore": "0.1.0"}),
        )
        .await;
    }
    if method == "GET" && path == "/pair/status" {
        return write_http_json(&mut stream, 200, serde_json::json!({"paired": false})).await;
    }

    if !(method == "GET" && path == "/ws") {
        return write_http_json(
            &mut stream,
            404,
            serde_json::json!({"ok": false, "error": "not_found"}),
        )
        .await;
    }

    let key = parse_ws_key(&req).ok_or(GatewayError::Handshake("missing sec-websocket-key".to_string()))?;
    let accept = compute_ws_accept(&key);
    let resp = format!(
        "HTTP/1.1 101 Switching Protocols\r\nConnection: Upgrade\r\nUpgrade: websocket\r\nSec-WebSocket-Accept: {accept}\r\n\r\n"
    );
    stream.write_all(resp.as_bytes()).await?;

    // 2) First message MUST be hello
    let hello_txt = read_ws_text_frame(&mut stream).await?;
    let hello: ClientFrameV1 = serde_json::from_str(&hello_txt)
        .map_err(|e| GatewayError::Protocol(format!("invalid hello json: {e}")))?;

    let (token, last_event_id) = match hello {
        ClientFrameV1::Hello { token, last_event_id } => (token, last_event_id),
        _ => {
            return Err(GatewayError::Protocol("first frame not hello".to_string()));
        }
    };

    let auth = state.auth.accept_or_pair(&token);
    let new_device_token = match auth {
        AuthDecision::Accepted { new_device_token } => new_device_token,
        AuthDecision::Rejected => return Err(GatewayError::Unauthorized),
    };

    // If this connection was established via pairing token, mint a device token and send it
    // back as a BaoEventV1. (Phase1: stored in-memory only.)
    // NOTE: For minimal correctness with lastEventId semantics, we persist this event.
    let mut paired_event_id: Option<i64> = None;
    if token.starts_with("p_") {
        if let Some(device_token) = new_device_token {
        let payload = serde_json::json!({"token": device_token});
        let evt = append_and_load_event(&state, now_ts(), "auth.paired", None, None, None, &payload).await?;
        paired_event_id = Some(evt.eventId);
        let txt = serde_json::to_string(&evt).unwrap();
        write_ws_text_frame(&mut stream, &txt).await?;
        }
    }

    // 3) Replay from storage by lastEventId (best-effort; phase1: may be empty)
    let replay = tokio::task::spawn_blocking({
        let sqlite_path = state.sqlite_path.clone();
        move || load_events_since(&sqlite_path, last_event_id, 5000)
    })
    .await
    .map_err(|e| GatewayError::Protocol(format!("join: {e}")))??;
    let mut cursor = last_event_id.unwrap_or(0);
    for evt in replay {
        if paired_event_id.is_some() && paired_event_id == Some(evt.eventId) {
            continue;
        }
        cursor = cursor.max(evt.eventId);
        let txt = serde_json::to_string(&evt).unwrap();
        write_ws_text_frame(&mut stream, &txt).await?;
    }
    let mut ticker = time::interval(Duration::from_millis(250));

    loop {
        tokio::select! {
            _ = ticker.tick() => {
                // tail new events from storage
                let new_events = tokio::task::spawn_blocking({
                    let sqlite_path = state.sqlite_path.clone();
                    let cursor = cursor;
                    move || load_events_since(&sqlite_path, Some(cursor), 5000)
                })
                .await
                .map_err(|e| GatewayError::Protocol(format!("join: {e}")))??;
                for evt in new_events {
                    cursor = cursor.max(evt.eventId);
                    let txt = serde_json::to_string(&evt).unwrap();
                    write_ws_text_frame(&mut stream, &txt).await?;
                }
            }
            r = read_ws_text_frame(&mut stream) => {
                let txt = match r {
                    Ok(t) => t,
                    Err(GatewayError::Io(e)) if e.kind() == std::io::ErrorKind::UnexpectedEof => return Ok(()),
                    Err(e) => return Err(e),
                };
                let frame: ClientFrameV1 = serde_json::from_str(&txt)
                    .map_err(|e| GatewayError::Protocol(format!("invalid frame json: {e}")))?;
                let evt = handle_client_command(&state, frame).await?;
                cursor = cursor.max(evt.eventId);
                let out = serde_json::to_string(&evt).unwrap();
                write_ws_text_frame(&mut stream, &out).await?;
            }
        }
    }
}

async fn handle_client_command(state: &GatewayState, frame: ClientFrameV1) -> Result<BaoEventV1, GatewayError> {
    let ts = now_ts();
    match frame {
        ClientFrameV1::Hello { .. } => Err(GatewayError::Protocol("duplicate hello".to_string())),
        ClientFrameV1::SendMessage { session_id, text } => {
            let payload = serde_json::json!({"sessionId": session_id, "text": text});
            append_and_load_event(state, ts, "message.send", Some(&session_id), None, None, &payload).await
        }
        ClientFrameV1::ListSessions => {
            let sessions = query_sessions(&state.sqlite_path).await?;
            let payload = serde_json::json!({"sessions": sessions});
            append_and_load_event(state, ts, "sessions.list", None, None, None, &payload).await
        }
        ClientFrameV1::ListTasks => {
            let tasks = query_tasks(&state.sqlite_path).await?;
            let payload = serde_json::json!({"tasks": tasks});
            append_and_load_event(state, ts, "tasks.list", None, None, None, &payload).await
        }
        ClientFrameV1::ListDimsums => {
            let dimsums = query_dimsums(&state.sqlite_path).await?;
            let payload = serde_json::json!({"dimsums": dimsums});
            append_and_load_event(state, ts, "dimsums.list", None, None, None, &payload).await
        }
        ClientFrameV1::ListMemories => {
            let memories = query_memories(&state.sqlite_path).await?;
            let payload = serde_json::json!({"memories": memories});
            append_and_load_event(state, ts, "memories.list", None, None, None, &payload).await
        }
        ClientFrameV1::GetSettings => {
            let settings = query_settings(&state.sqlite_path).await?;
            let payload = serde_json::json!({"settings": settings});
            append_and_load_event(state, ts, "settings.get", None, None, None, &payload).await
        }
    }
}

async fn append_and_load_event(
    state: &GatewayState,
    ts: i64,
    ty: &str,
    session_id: Option<&str>,
    message_id: Option<&str>,
    device_id: Option<&str>,
    payload: &Value,
) -> Result<BaoEventV1, GatewayError> {
    let event_id = tokio::task::spawn_blocking({
        let sqlite_path = state.sqlite_path.clone();
        let ty = ty.to_string();
        let session_id = session_id.map(|s| s.to_string());
        let message_id = message_id.map(|s| s.to_string());
        let device_id = device_id.map(|s| s.to_string());
        let payload_json = serde_json::to_string(payload).unwrap_or_else(|_| "{}".to_string());
        move || {
            let conn = Connection::open(sqlite_path)?;
            conn.pragma_update(None, "foreign_keys", "ON")?;
            conn.execute(
                "INSERT INTO events(ts, type, session_id, message_id, device_id, payload_json) VALUES (?1, ?2, ?3, ?4, ?5, ?6)",
                params![ts, ty, session_id, message_id, device_id, payload_json],
            )?;
            Ok::<_, GatewayError>(conn.last_insert_rowid())
        }
    })
    .await
    .map_err(|e| GatewayError::Protocol(format!("join: {e}")))??;

    Ok(BaoEventV1 {
        eventId: event_id,
        ts,
        r#type: ty.to_string(),
        sessionId: session_id.map(|s| s.to_string()),
        messageId: message_id.map(|s| s.to_string()),
        deviceId: device_id.map(|s| s.to_string()),
        payload: payload.clone(),
    })
}

async fn read_http_request(stream: &mut TcpStream) -> Result<String, GatewayError> {
    let mut buf = Vec::with_capacity(2048);
    let mut tmp = [0u8; 512];
    loop {
        let n = stream.read(&mut tmp).await?;
        if n == 0 {
            return Err(GatewayError::Handshake("eof".to_string()));
        }
        buf.extend_from_slice(&tmp[..n]);
        if buf.windows(4).any(|w| w == b"\r\n\r\n") {
            break;
        }
        if buf.len() > 16 * 1024 {
            return Err(GatewayError::Handshake("request too large".to_string()));
        }
    }
    Ok(String::from_utf8_lossy(&buf).to_string())
}

fn parse_ws_key(req: &str) -> Option<String> {
    for line in req.split("\r\n") {
        let lower = line.to_ascii_lowercase();
        if lower.starts_with("sec-websocket-key:") {
            return Some(line.splitn(2, ':').nth(1)?.trim().to_string());
        }
    }
    None
}

fn compute_ws_accept(key: &str) -> String {
    // RFC6455: accept = base64( SHA1(key + GUID) )
    const GUID: &str = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11";
    let mut h = Sha1::new();
    h.update(key.as_bytes());
    h.update(GUID.as_bytes());
    let digest = h.finalize();
    general_purpose::STANDARD.encode(digest)
}

fn parse_http_request_line(req: &str) -> Option<(String, String)> {
    let line = req.lines().next()?;
    let mut it = line.split_whitespace();
    let method = it.next()?.to_string();
    let path = it.next()?.to_string();
    Some((method, path))
}

async fn write_http_json(stream: &mut TcpStream, status: u16, body: Value) -> Result<(), GatewayError> {
    let b = serde_json::to_vec(&body).unwrap_or_else(|_| b"{}".to_vec());
    let reason = match status {
        200 => "OK",
        404 => "Not Found",
        _ => "OK",
    };
    let resp = format!(
        "HTTP/1.1 {status} {reason}\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n",
        b.len()
    );
    stream.write_all(resp.as_bytes()).await?;
    stream.write_all(&b).await?;
    Ok(())
}

async fn query_sessions(sqlite_path: &str) -> Result<Vec<Value>, GatewayError> {
    let p = sqlite_path.to_string();
    tokio::task::spawn_blocking(move || {
        let conn = rusqlite::Connection::open(p)?;
        let mut stmt = conn.prepare(
            "SELECT session_id, title, created_at, updated_at FROM sessions ORDER BY updated_at DESC LIMIT 200",
        )?;
        let rows = stmt.query_map([], |r| {
            let session_id: String = r.get(0)?;
            let title: Option<String> = r.get(1)?;
            let created_at: i64 = r.get(2)?;
            let updated_at: i64 = r.get(3)?;
            Ok(serde_json::json!({
                "sessionId": session_id,
                "title": title,
                "createdAt": created_at,
                "updatedAt": updated_at
            }))
        })?;
        let mut out = vec![];
        for r in rows {
            out.push(r?);
        }
        Ok::<_, GatewayError>(out)
    })
    .await
    .map_err(|e| GatewayError::Protocol(format!("join: {e}")))?
}

async fn query_tasks(sqlite_path: &str) -> Result<Vec<Value>, GatewayError> {
    let p = sqlite_path.to_string();
    tokio::task::spawn_blocking(move || {
        let conn = rusqlite::Connection::open(p)?;
        let mut stmt = conn.prepare(
            "SELECT task_id, title, enabled, schedule_kind, run_at_ts, interval_ms, cron, timezone, next_run_at, last_run_at, last_status, last_error, tool_dimsum_id, tool_name, tool_args_json, policy_json, kill_switch_group, created_at, updated_at \
             FROM tasks ORDER BY updated_at DESC LIMIT 200",
        )?;
        let rows = stmt.query_map([], |r| {
            let tool_args_json: String = r.get(14)?;
            let policy_json: Option<String> = r.get(15)?;
            Ok(serde_json::json!({
                "taskId": r.get::<_, String>(0)?,
                "title": r.get::<_, String>(1)?,
                "enabled": r.get::<_, i64>(2)? == 1,
                "schedule": {
                    "kind": r.get::<_, String>(3)?,
                    "runAtTs": r.get::<_, Option<i64>>(4)?,
                    "intervalMs": r.get::<_, Option<i64>>(5)?,
                    "cron": r.get::<_, Option<String>>(6)?,
                    "timezone": r.get::<_, Option<String>>(7)?
                },
                "nextRunAt": r.get::<_, Option<i64>>(8)?,
                "lastRunAt": r.get::<_, Option<i64>>(9)?,
                "lastStatus": r.get::<_, Option<String>>(10)?,
                "lastError": r.get::<_, Option<String>>(11)?,
                "tool": {
                    "dimsumId": r.get::<_, String>(12)?,
                    "toolName": r.get::<_, String>(13)?,
                    "args": serde_json::from_str::<Value>(&tool_args_json).unwrap_or(Value::Null)
                },
                "policy": policy_json.and_then(|s| serde_json::from_str::<Value>(&s).ok()),
                "killSwitchGroup": r.get::<_, Option<String>>(16)?,
                "createdAt": r.get::<_, i64>(17)?,
                "updatedAt": r.get::<_, i64>(18)?
            }))
        })?;
        let mut out = vec![];
        for r in rows {
            out.push(r?);
        }
        Ok::<_, GatewayError>(out)
    })
    .await
    .map_err(|e| GatewayError::Protocol(format!("join: {e}")))?
}

async fn query_dimsums(sqlite_path: &str) -> Result<Vec<Value>, GatewayError> {
    let p = sqlite_path.to_string();
    tokio::task::spawn_blocking(move || {
        let conn = rusqlite::Connection::open(p)?;
        let mut stmt = conn.prepare(
            "SELECT dimsum_id, enabled, channel, version, manifest_json, installed_at, updated_at FROM dimsums ORDER BY updated_at DESC LIMIT 200",
        )?;
        let rows = stmt.query_map([], |r| {
            let manifest_json: String = r.get(4)?;
            Ok(serde_json::json!({
                "dimsumId": r.get::<_, String>(0)?,
                "enabled": r.get::<_, i64>(1)? == 1,
                "channel": r.get::<_, String>(2)?,
                "version": r.get::<_, String>(3)?,
                "manifest": serde_json::from_str::<Value>(&manifest_json).unwrap_or(Value::Null),
                "installedAt": r.get::<_, i64>(5)?,
                "updatedAt": r.get::<_, i64>(6)?
            }))
        })?;
        let mut out = vec![];
        for r in rows {
            out.push(r?);
        }
        Ok::<_, GatewayError>(out)
    })
    .await
    .map_err(|e| GatewayError::Protocol(format!("join: {e}")))?
}

async fn query_memories(sqlite_path: &str) -> Result<Vec<Value>, GatewayError> {
    let p = sqlite_path.to_string();
    tokio::task::spawn_blocking(move || {
        let conn = rusqlite::Connection::open(p)?;
        let mut stmt = conn.prepare(
            "SELECT memory_id, namespace, kind, title, score, status, updated_at FROM memory_items ORDER BY updated_at DESC LIMIT 200",
        )?;
        let rows = stmt.query_map([], |r| {
            Ok(serde_json::json!({
                "id": r.get::<_, String>(0)?,
                "namespace": r.get::<_, String>(1)?,
                "kind": r.get::<_, String>(2)?,
                "title": r.get::<_, String>(3)?,
                "score": r.get::<_, f64>(4)?,
                "status": r.get::<_, String>(5)?,
                "updatedAt": r.get::<_, i64>(6)?
            }))
        })?;
        let mut out = vec![];
        for r in rows {
            out.push(r?);
        }
        Ok::<_, GatewayError>(out)
    })
    .await
    .map_err(|e| GatewayError::Protocol(format!("join: {e}")))?
}

async fn query_settings(sqlite_path: &str) -> Result<Vec<Value>, GatewayError> {
    let p = sqlite_path.to_string();
    tokio::task::spawn_blocking(move || {
        let conn = rusqlite::Connection::open(p)?;
        let mut stmt = conn.prepare(
            "SELECT key, value_json, updated_at FROM settings ORDER BY key ASC",
        )?;
        let rows = stmt.query_map([], |r| {
            let key: String = r.get(0)?;
            let value_json: String = r.get(1)?;
            let updated_at: i64 = r.get(2)?;
            Ok(serde_json::json!({
                "key": key,
                "value": serde_json::from_str::<Value>(&value_json).unwrap_or(Value::Null),
                "updatedAt": updated_at
            }))
        })?;
        let mut out = vec![];
        for r in rows {
            out.push(r?);
        }
        Ok::<_, GatewayError>(out)
    })
    .await
    .map_err(|e| GatewayError::Protocol(format!("join: {e}")))?
}

async fn read_ws_text_frame(stream: &mut TcpStream) -> Result<String, GatewayError> {
    let mut hdr = [0u8; 2];
    stream.read_exact(&mut hdr).await?;

    let fin = (hdr[0] & 0x80) != 0;
    let opcode = hdr[0] & 0x0f;
    if !fin {
        return Err(GatewayError::Protocol("fragmented frames not supported".to_string()));
    }
    if opcode == 0x8 {
        return Err(GatewayError::Protocol("close".to_string()));
    }
    if opcode != 0x1 {
        return Err(GatewayError::Protocol("only text frames supported".to_string()));
    }

    let masked = (hdr[1] & 0x80) != 0;
    if !masked {
        return Err(GatewayError::Protocol("client frames must be masked".to_string()));
    }
    let mut len = (hdr[1] & 0x7f) as u64;
    if len == 126 {
        let mut b = [0u8; 2];
        stream.read_exact(&mut b).await?;
        len = u16::from_be_bytes(b) as u64;
    } else if len == 127 {
        let mut b = [0u8; 8];
        stream.read_exact(&mut b).await?;
        len = u64::from_be_bytes(b);
    }
    if len > 2 * 1024 * 1024 {
        return Err(GatewayError::Protocol("frame too large".to_string()));
    }

    let mut mask = [0u8; 4];
    stream.read_exact(&mut mask).await?;
    let mut payload = vec![0u8; len as usize];
    stream.read_exact(&mut payload).await?;
    for (i, b) in payload.iter_mut().enumerate() {
        *b ^= mask[i % 4];
    }
    Ok(String::from_utf8(payload).map_err(|e| GatewayError::Protocol(format!("utf8: {e}")))?)
}

async fn write_ws_text_frame(stream: &mut TcpStream, text: &str) -> Result<(), GatewayError> {
    let bytes = text.as_bytes();
    let mut out = Vec::with_capacity(bytes.len() + 16);
    out.push(0x80 | 0x1); // FIN + text
    if bytes.len() < 126 {
        out.push(bytes.len() as u8);
    } else if bytes.len() <= u16::MAX as usize {
        out.push(126);
        out.extend_from_slice(&(bytes.len() as u16).to_be_bytes());
    } else {
        out.push(127);
        out.extend_from_slice(&(bytes.len() as u64).to_be_bytes());
    }
    out.extend_from_slice(bytes);
    stream.write_all(&out).await?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::net::TcpStream as StdTcpStream;
    use tempfile::TempDir;
    use tokio::net::TcpStream;

    #[derive(Debug, Deserialize)]
    struct TestBaoEventV1 {
        #[serde(rename = "eventId")]
        event_id: i64,
        ts: i64,
        #[serde(rename = "type")]
        ty: String,
        #[serde(rename = "sessionId")]
        session_id: Option<String>,
        #[serde(rename = "messageId")]
        message_id: Option<String>,
        #[serde(rename = "deviceId")]
        device_id: Option<String>,
        payload: Value,
    }

    fn random_ws_key() -> String {
        let mut bytes = [0u8; 16];
        OsRng.fill_bytes(&mut bytes);
        general_purpose::STANDARD.encode(bytes)
    }

    async fn ws_handshake(addr: SocketAddr) -> Result<TcpStream, GatewayError> {
        let mut s = TcpStream::connect(addr).await?;
        let key = random_ws_key();
        let req = format!(
            "GET /ws HTTP/1.1\r\nHost: {}\r\nConnection: Upgrade\r\nUpgrade: websocket\r\nSec-WebSocket-Version: 13\r\nSec-WebSocket-Key: {}\r\n\r\n",
            addr, key
        );
        s.write_all(req.as_bytes()).await?;

        // read response headers
        let mut buf = Vec::with_capacity(1024);
        let mut tmp = [0u8; 256];
        loop {
            let n = s.read(&mut tmp).await?;
            if n == 0 {
                return Err(GatewayError::Handshake("eof".to_string()));
            }
            buf.extend_from_slice(&tmp[..n]);
            if buf.windows(4).any(|w| w == b"\r\n\r\n") {
                break;
            }
            if buf.len() > 16 * 1024 {
                return Err(GatewayError::Handshake("response too large".to_string()));
            }
        }
        let txt = String::from_utf8_lossy(&buf);
        if !txt.starts_with("HTTP/1.1 101") {
            return Err(GatewayError::Handshake(format!("unexpected response: {txt}")));
        }
        Ok(s)
    }

    async fn write_masked_text_frame(stream: &mut TcpStream, text: &str) -> Result<(), GatewayError> {
        let bytes = text.as_bytes();
        let mut out = Vec::with_capacity(bytes.len() + 32);
        out.push(0x80 | 0x1); // FIN + text
        if bytes.len() < 126 {
            out.push(0x80 | (bytes.len() as u8));
        } else if bytes.len() <= u16::MAX as usize {
            out.push(0x80 | 126);
            out.extend_from_slice(&(bytes.len() as u16).to_be_bytes());
        } else {
            out.push(0x80 | 127);
            out.extend_from_slice(&(bytes.len() as u64).to_be_bytes());
        }

        let mut mask = [0u8; 4];
        OsRng.fill_bytes(&mut mask);
        out.extend_from_slice(&mask);
        for (i, b) in bytes.iter().enumerate() {
            out.push(*b ^ mask[i % 4]);
        }

        stream.write_all(&out).await?;
        Ok(())
    }

    async fn read_unmasked_text_frame(stream: &mut TcpStream) -> Result<String, GatewayError> {
        let mut hdr = [0u8; 2];
        stream.read_exact(&mut hdr).await?;
        let fin = (hdr[0] & 0x80) != 0;
        let opcode = hdr[0] & 0x0f;
        if !fin {
            return Err(GatewayError::Protocol("fragmented frames not supported".to_string()));
        }
        if opcode != 0x1 {
            return Err(GatewayError::Protocol("expected text frame".to_string()));
        }
        let masked = (hdr[1] & 0x80) != 0;
        if masked {
            return Err(GatewayError::Protocol("server frames must be unmasked".to_string()));
        }
        let mut len = (hdr[1] & 0x7f) as u64;
        if len == 126 {
            let mut b = [0u8; 2];
            stream.read_exact(&mut b).await?;
            len = u16::from_be_bytes(b) as u64;
        } else if len == 127 {
            let mut b = [0u8; 8];
            stream.read_exact(&mut b).await?;
            len = u64::from_be_bytes(b);
        }
        let mut payload = vec![0u8; len as usize];
        stream.read_exact(&mut payload).await?;
        Ok(String::from_utf8(payload).map_err(|e| GatewayError::Protocol(format!("utf8: {e}")))?)
    }

    fn temp_sqlite_path() -> (TempDir, String) {
        let dir = TempDir::new().expect("tempdir");
        let p = dir.path().join("bao.sqlite");
        (dir, p.to_string_lossy().to_string())
    }

    #[tokio::test]
    async fn invalid_token_rejected() {
        let (_dir, sqlite_path) = temp_sqlite_path();
        let (server, _handle) = GatewayServer::open(sqlite_path).expect("open");

        let listener = TcpListener::bind((Ipv4Addr::LOCALHOST, 0)).await.expect("bind");
        let addr = listener.local_addr().expect("local_addr");
        let jh = tokio::spawn(async move { server.start_with_listener(listener).await });

        let mut ws = ws_handshake(addr).await.expect("handshake");
        let hello = serde_json::json!({"type": "hello", "token": "nope", "lastEventId": null});
        write_masked_text_frame(&mut ws, &hello.to_string()).await.expect("write");

        let r = time::timeout(Duration::from_millis(300), read_unmasked_text_frame(&mut ws)).await;
        assert!(r.is_err() || r.unwrap().is_err(), "expected connection drop");

        jh.abort();
    }

    #[tokio::test]
    async fn reconnect_replays_events_after_last_event_id() {
        let (_dir, sqlite_path) = temp_sqlite_path();
        let (server, handle) = GatewayServer::open(sqlite_path).expect("open");

        let listener = TcpListener::bind((Ipv4Addr::LOCALHOST, 0)).await.expect("bind");
        let addr = listener.local_addr().expect("local_addr");
        let jh = tokio::spawn(async move { server.start_with_listener(listener).await });

        let pairing = handle.create_pairing_token();

        // first connection: pair
        let mut ws1 = ws_handshake(addr).await.expect("handshake1");
        let hello1 = serde_json::json!({"type": "hello", "token": pairing, "lastEventId": null});
        write_masked_text_frame(&mut ws1, &hello1.to_string()).await.expect("write hello1");

        // auth.paired should come first
        let paired_txt = read_unmasked_text_frame(&mut ws1).await.expect("read paired");
        let paired_evt: TestBaoEventV1 = serde_json::from_str(&paired_txt).expect("parse paired");
        assert_eq!(paired_evt.ty, "auth.paired");
        let device_token = paired_evt
            .payload
            .get("token")
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .to_string();
        assert!(!device_token.is_empty(), "device token should be minted");

        // append one event
        let cmd = serde_json::json!({"type": "sendMessage", "sessionId": "s1", "text": "hi"});
        write_masked_text_frame(&mut ws1, &cmd.to_string()).await.expect("write sendMessage");
        let msg_txt = read_unmasked_text_frame(&mut ws1).await.expect("read msg");
        let msg_evt: TestBaoEventV1 = serde_json::from_str(&msg_txt).expect("parse msg");
        assert_eq!(msg_evt.ty, "message.send");
        assert!(msg_evt.event_id > paired_evt.event_id);

        drop(ws1);

        // reconnect with lastEventId = paired event id, should replay message.send
        let mut ws2 = ws_handshake(addr).await.expect("handshake2");
        let hello2 = serde_json::json!({"type": "hello", "token": device_token, "lastEventId": paired_evt.event_id});
        write_masked_text_frame(&mut ws2, &hello2.to_string()).await.expect("write hello2");

        let replay_txt = time::timeout(Duration::from_secs(1), read_unmasked_text_frame(&mut ws2))
            .await
            .expect("timeout")
            .expect("read replay");
        let replay_evt: TestBaoEventV1 = serde_json::from_str(&replay_txt).expect("parse replay");
        assert_eq!(replay_evt.ty, "message.send");
        assert_eq!(replay_evt.event_id, msg_evt.event_id);

        jh.abort();
    }
}

// -----------------------------
// Errors
// -----------------------------

#[derive(Debug, Error)]
pub enum GatewayError {
    #[error("io: {0}")]
    Io(#[from] std::io::Error),

    #[error("sqlite: {0}")]
    Sqlite(#[from] rusqlite::Error),

    #[error("unauthorized")]
    Unauthorized,

    #[error("handshake: {0}")]
    Handshake(String),

    #[error("protocol: {0}")]
    Protocol(String),
}
