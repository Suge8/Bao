use std::{
    collections::{HashMap, HashSet},
    fs,
    net::{IpAddr, Ipv4Addr, SocketAddr},
    str::FromStr,
    sync::{Arc, Mutex},
    time::{Duration, SystemTime, UNIX_EPOCH},
};

use bao_api::{BaoEventV1, MemoryHitV1, MemoryMutationPlanV1, TaskSpecV1};
use bao_engine::scheduler::SchedulerService;
use bao_engine::storage::SqliteStorage;
use bao_plugin_host::process_runner::ProcessToolRunner;
use bao_storage::{
    AuditEventRecord, MemoryItemRecord, MemoryLinkRecord, MemoryVersionRecord, Storage,
    StorageError,
};
use chrono_tz::Tz;
use cron::Schedule;
use base64::{engine::general_purpose, Engine as _};
use hex;
use rand::{rngs::OsRng, RngCore};
use rusqlite::{params, Connection, OptionalExtension};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use sha1::{Digest as _, Sha1};
use thiserror::Error;
use tokio::{
    io::{AsyncReadExt, AsyncWriteExt},
    net::{TcpListener, TcpStream},
    time,
};

const TRUSTED_SIGNER_BUNDLED: &str = "bao.bundled.release";
const TRUSTED_SIGNER_COMMUNITY: &str = "bao.community.release";

const DIMSUM_TRUST_UNTRUSTED_SOURCE: &str = "DIMSUM_TRUST_UNTRUSTED_SOURCE";
const DIMSUM_TRUST_INVALID_SIGNATURE: &str = "DIMSUM_TRUST_INVALID_SIGNATURE";
const DIMSUM_TRUST_TAMPERED_MANIFEST: &str = "DIMSUM_TRUST_TAMPERED_MANIFEST";
const DIMSUM_TRUST_DOWNGRADE_BLOCKED: &str = "DIMSUM_TRUST_DOWNGRADE_BLOCKED";
const DIMSUM_UPGRADE_FAILED_ROLLBACK_APPLIED: &str = "DIMSUM_UPGRADE_FAILED_ROLLBACK_APPLIED";

const GATEWAY_SOURCE_PUBLIC_REJECTED: &str = "GATEWAY_SOURCE_PUBLIC_REJECTED";

#[derive(Debug, Clone)]
struct DimsumTrustError {
    code: &'static str,
    reason: String,
}

impl DimsumTrustError {
    fn protocol_message(&self) -> String {
        format!("{}: {}", self.code, self.reason)
    }
}

#[derive(Debug, Clone)]
struct BundledUpgradeFailure {
    code: &'static str,
    reason: String,
    dimsum_id: String,
    channel: Option<String>,
    manifest_path: Option<String>,
    installed_version: Option<String>,
    incoming_version: Option<String>,
}

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
    scheduler: Arc<SchedulerService>,
    storage: Arc<Storage>,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct GatewayDevice {
    pub device_id: String,
    pub connected: bool,
}

impl GatewayHandle {
    /// Expose underlying SQLite path for desktop glue.
    pub fn sqlite_path(&self) -> String {
        self.state.sqlite_path.clone()
    }

    pub fn create_pairing_token(&self) -> String {
        let token = self.state.auth.create_pairing();
        let now_ts = now_ts();
        let payload = serde_json::json!({"token": token});
        let _ = self.storage.insert_audit_event(
            now_ts,
            "auth.pairing.create",
            "auth",
            "pairing",
            &payload,
        );
        token
    }

    pub fn revoke_pairing_token(&self, token: &str) {
        self.state.auth.revoke(token);
        let now_ts = now_ts();
        let payload = serde_json::json!({"token": token});
        let _ = self.storage.insert_audit_event(
            now_ts,
            "auth.pairing.revoke",
            "auth",
            "pairing",
            &payload,
        );
    }

    pub fn list_gateway_devices(&self) -> Vec<GatewayDevice> {
        self.state.auth.list_devices()
    }

    pub fn revoke_gateway_device(&self, token: &str) {
        self.state.auth.revoke(token);
        let now_ts = now_ts();
        let payload = serde_json::json!({"token": token});
        let _ = self
            .storage
            .insert_audit_event(now_ts, "auth.device.revoke", "auth", "device", &payload);
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

    pub async fn send_message(
        &self,
        session_id: String,
        text: String,
    ) -> Result<BaoEventV1, GatewayError> {
        let ts = now_ts();
        ensure_session_exists(&self.state.sqlite_path, &session_id, ts).await?;
        let sid = session_id.clone();
        let payload = serde_json::json!({"sessionId": session_id, "text": text});
        append_and_load_event(
            &self.state,
            ts,
            "message.send",
            Some(sid.as_str()),
            None,
            None,
            &payload,
        )
        .await
    }

    pub async fn create_session(
        &self,
        session_id: String,
        title: Option<String>,
    ) -> Result<BaoEventV1, GatewayError> {
        let ts = now_ts();
        if session_id.trim().is_empty() {
            return Err(GatewayError::Protocol(
                "session id cannot be empty".to_string(),
            ));
        }
        let sid = session_id.clone();

        tokio::task::spawn_blocking({
            let sqlite_path = self.state.sqlite_path.clone();
            let session_id = session_id.clone();
            let title = title.clone();
            move || {
                let conn = Connection::open(sqlite_path)?;
                conn.pragma_update(None, "foreign_keys", "ON")?;
                conn.execute(
                    "INSERT INTO sessions(session_id, title, created_at, updated_at) VALUES (?1, ?2, ?3, ?3) \
                     ON CONFLICT(session_id) DO UPDATE SET title=COALESCE(excluded.title, sessions.title), updated_at=excluded.updated_at",
                    params![session_id, title, ts],
                )?;
                Ok::<_, GatewayError>(())
            }
        })
        .await
        .map_err(|e| GatewayError::Protocol(format!("join: {e}")))??;

        let payload = serde_json::json!({
            "sessionId": session_id,
            "title": title,
        });
        append_and_load_event(
            &self.state,
            ts,
            "sessions.create",
            Some(sid.as_str()),
            None,
            None,
            &payload,
        )
        .await
    }

    pub async fn list_sessions(&self) -> Result<BaoEventV1, GatewayError> {
        let sessions = query_sessions(&self.state.sqlite_path).await?;
        let payload = serde_json::json!({"sessions": sessions});
        append_and_load_event(
            &self.state,
            now_ts(),
            "sessions.list",
            None,
            None,
            None,
            &payload,
        )
        .await
    }

    pub async fn delete_session(&self, session_id: String) -> Result<BaoEventV1, GatewayError> {
        let ts = now_ts();
        if session_id.trim().is_empty() {
            return Err(GatewayError::Protocol(
                "session id cannot be empty".to_string(),
            ));
        }
        let sid = session_id.clone();

        tokio::task::spawn_blocking({
            let sqlite_path = self.state.sqlite_path.clone();
            let session_id = session_id.clone();
            move || {
                let mut conn = Connection::open(sqlite_path)?;
                conn.pragma_update(None, "foreign_keys", "ON")?;
                let tx = conn.transaction()?;
                tx.execute(
                    "DELETE FROM tool_calls WHERE session_id=?1",
                    params![&session_id],
                )?;
                tx.execute("DELETE FROM messages WHERE session_id=?1", params![&session_id])?;
                let deleted = tx.execute("DELETE FROM sessions WHERE session_id=?1", params![&session_id])?;
                if deleted == 0 {
                    return Err(GatewayError::Protocol("session not found".to_string()));
                }
                tx.commit()?;
                Ok::<_, GatewayError>(())
            }
        })
        .await
        .map_err(|e| GatewayError::Protocol(format!("join: {e}")))??;

        let payload = serde_json::json!({"sessionId": sid});
        append_and_load_event(
            &self.state,
            ts,
            "sessions.delete",
            Some(sid.as_str()),
            None,
            None,
            &payload,
        )
        .await
    }

    pub async fn list_tasks(&self) -> Result<BaoEventV1, GatewayError> {
        let tasks = query_tasks(&self.state.sqlite_path).await?;
        let payload = serde_json::json!({"tasks": tasks});
        append_and_load_event(
            &self.state,
            now_ts(),
            "tasks.list",
            None,
            None,
            None,
            &payload,
        )
        .await
    }

    pub async fn create_task(&self, spec: TaskSpecV1) -> Result<BaoEventV1, GatewayError> {
        validate_task_spec(&spec)?;
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

                let computed_next_run_at = bao_storage::compute_task_next_run_at(
                    schedule_kind,
                    spec.schedule.runAtTs,
                    spec.schedule.intervalMs,
                    spec.schedule.cron.as_deref(),
                    spec.schedule.timezone.as_deref(),
                    ts,
                );

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
                        computed_next_run_at,
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
        validate_task_spec(&spec)?;
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

                let computed_next_run_at = bao_storage::compute_task_next_run_at(
                    schedule_kind,
                    spec.schedule.runAtTs,
                    spec.schedule.intervalMs,
                    spec.schedule.cron.as_deref(),
                    spec.schedule.timezone.as_deref(),
                    ts,
                );

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
                        computed_next_run_at,
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

                let (schedule_kind, run_at_ts, interval_ms, cron, timezone): (
                    String,
                    Option<i64>,
                    Option<i64>,
                    Option<String>,
                    Option<String>,
                ) = conn.query_row(
                    "SELECT schedule_kind, run_at_ts, interval_ms, cron, timezone FROM tasks WHERE task_id=?1",
                    params![task_id.clone()],
                    |r| Ok((r.get(0)?, r.get(1)?, r.get(2)?, r.get(3)?, r.get(4)?)),
                )?;

                let computed_next_run_at = bao_storage::compute_task_next_run_at(
                    &schedule_kind,
                    run_at_ts,
                    interval_ms,
                    cron.as_deref(),
                    timezone.as_deref(),
                    ts,
                );

                conn.execute(
                    "UPDATE tasks SET enabled=1, next_run_at=?3, updated_at=?2 WHERE task_id=?1",
                    params![task_id, ts, computed_next_run_at],
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
        let ts = now_ts();
        let task_id_str = task_id.clone();
        let payload = serde_json::json!({"taskId": task_id});
        let evt =
            append_and_load_event(&self.state, ts, "tasks.runNow", None, None, None, &payload)
                .await?;
        self.scheduler.run_task_now(&task_id_str, ts);
        Ok(evt)
    }

    pub async fn search_index(
        &self,
        query: String,
        limit: i64,
    ) -> Result<BaoEventV1, GatewayError> {
        let hits = memory_search_index(&self.state.sqlite_path, &query, limit).await?;
        let payload = serde_json::json!({"query": query, "hits": hits});
        append_and_load_event(
            &self.state,
            now_ts(),
            "memory.searchIndex",
            None,
            None,
            None,
            &payload,
        )
        .await
    }

    pub async fn get_items(&self, ids: Vec<String>) -> Result<BaoEventV1, GatewayError> {
        let items = memory_get_items(&self.state.sqlite_path, &ids).await?;
        let payload = serde_json::json!({"ids": ids, "items": items});
        append_and_load_event(
            &self.state,
            now_ts(),
            "memory.getItems",
            None,
            None,
            None,
            &payload,
        )
        .await
    }

    pub async fn get_timeline(
        &self,
        namespace: Option<String>,
    ) -> Result<BaoEventV1, GatewayError> {
        let timeline = memory_get_timeline(&self.state.sqlite_path, namespace.clone()).await?;
        let payload = serde_json::json!({"namespace": namespace, "timeline": timeline});
        append_and_load_event(
            &self.state,
            now_ts(),
            "memory.getTimeline",
            None,
            None,
            None,
            &payload,
        )
        .await
    }

    pub async fn list_memory_versions(
        &self,
        memory_id: String,
    ) -> Result<BaoEventV1, GatewayError> {
        if memory_id.trim().is_empty() {
            return Err(GatewayError::Protocol(
                "memory id cannot be empty".to_string(),
            ));
        }

        let versions = tokio::task::spawn_blocking({
            let storage = self.storage.clone();
            let memory_id = memory_id.clone();
            move || storage.list_memory_versions(&memory_id)
        })
        .await
        .map_err(|e| GatewayError::Protocol(format!("join: {e}")))??;

        let payload = serde_json::json!({"memoryId": memory_id, "versions": versions});
        append_and_load_event(
            &self.state,
            now_ts(),
            "memory.listVersions",
            None,
            None,
            None,
            &payload,
        )
        .await
    }

    pub async fn apply_mutation_plan(
        &self,
        _plan: MemoryMutationPlanV1,
    ) -> Result<BaoEventV1, GatewayError> {
        let ts = now_ts();
        let plan = _plan;
        for mutation in plan.mutations.iter() {
            match mutation.op {
                bao_api::MemoryMutationOpV1::UPSERT => {
                    if let Some(mem) = mutation.memory.as_ref() {
                        let memory_id = mem
                            .id
                            .clone()
                            .unwrap_or_else(|| format!("m_{}", random_token()));
                        let item = MemoryItemRecord {
                            memory_id: memory_id.clone(),
                            namespace: mem.namespace.clone(),
                            kind: mem.kind.clone(),
                            title: mem.title.clone(),
                            content: mem.content.clone(),
                            json: mem
                                .json
                                .as_ref()
                                .and_then(|j| serde_json::to_string(j).ok()),
                            score: mem.score.unwrap_or(0.0),
                            status: mem.status.clone().unwrap_or_else(|| "active".to_string()),
                            source_hash: mem.sourceHash.clone(),
                            created_at: ts,
                            updated_at: ts,
                            last_injected_at: None,
                            inject_count: 0,
                        };
                        self.storage.upsert_memory_item(&item)?;
                        let version = MemoryVersionRecord {
                            version_id: format!("v_{}", random_token()),
                            memory_id: memory_id.clone(),
                            prev_version_id: None,
                            op: "UPSERT".to_string(),
                            diff_json: serde_json::to_string(&mutation)
                                .unwrap_or_else(|_| "{}".to_string()),
                            actor: "gateway".to_string(),
                            created_at: ts,
                        };
                        self.storage.insert_memory_version(&version)?;
                        let _ = self.storage.insert_audit_event(
                            ts,
                            "memory.upsert",
                            "memory",
                            &memory_id,
                            &serde_json::json!({"planId": plan.planId}),
                        );
                    }
                }
                bao_api::MemoryMutationOpV1::SUPERSEDE => {
                    if let Some(sup) = mutation.supersede.as_ref() {
                        let old_memory_snapshot = self.storage.get_memory_item(&sup.oldId)?;
                        let _ = self.storage.delete_memory_item(&sup.oldId);
                        if let Some(mem) = mutation.memory.as_ref() {
                            let memory_id = mem.id.clone().unwrap_or_else(|| sup.newId.clone());
                            let item = MemoryItemRecord {
                                memory_id: memory_id.clone(),
                                namespace: mem.namespace.clone(),
                                kind: mem.kind.clone(),
                                title: mem.title.clone(),
                                content: mem.content.clone(),
                                json: mem
                                    .json
                                    .as_ref()
                                    .and_then(|j| serde_json::to_string(j).ok()),
                                score: mem.score.unwrap_or(0.0),
                                status: mem.status.clone().unwrap_or_else(|| "active".to_string()),
                                source_hash: mem.sourceHash.clone(),
                                created_at: ts,
                                updated_at: ts,
                                last_injected_at: None,
                                inject_count: 0,
                            };
                            self.storage.upsert_memory_item(&item)?;
                        }
                        let version = MemoryVersionRecord {
                            version_id: format!("v_{}", random_token()),
                            memory_id: sup.newId.clone(),
                            prev_version_id: None,
                            op: "SUPERSEDE".to_string(),
                            diff_json: serde_json::to_string(&serde_json::json!({
                                "mutation": mutation,
                                "oldMemory": old_memory_snapshot.map(|item| memory_record_to_json(&item)),
                            }))
                            .unwrap_or_else(|_| "{}".to_string()),
                            actor: "gateway".to_string(),
                            created_at: ts,
                        };
                        self.storage.insert_memory_version(&version)?;
                        let _ = self.storage.insert_audit_event(
                            ts,
                            "memory.supersede",
                            "memory",
                            &sup.newId,
                            &serde_json::json!({"oldId": sup.oldId, "reason": mutation.reason}),
                        );
                    }
                }
                bao_api::MemoryMutationOpV1::DELETE => {
                    if let Some(del) = mutation.delete.as_ref() {
                        let deleted_memory_snapshot = self.storage.get_memory_item(&del.id)?;
                        let _ = self.storage.delete_memory_item(&del.id);
                        let version = MemoryVersionRecord {
                            version_id: format!("v_{}", random_token()),
                            memory_id: del.id.clone(),
                            prev_version_id: None,
                            op: "DELETE".to_string(),
                            diff_json: serde_json::to_string(&serde_json::json!({
                                "mutation": mutation,
                                "deletedMemory": deleted_memory_snapshot.map(|item| memory_record_to_json(&item)),
                            }))
                            .unwrap_or_else(|_| "{}".to_string()),
                            actor: "gateway".to_string(),
                            created_at: ts,
                        };
                        self.storage.insert_memory_version(&version)?;
                        let _ = self.storage.insert_audit_event(
                            ts,
                            "memory.delete",
                            "memory",
                            &del.id,
                            &serde_json::json!({"reason": mutation.reason}),
                        );
                    }
                }
                bao_api::MemoryMutationOpV1::LINK => {
                    if let Some(link) = mutation.link.as_ref() {
                        let evidence = &link.evidence;
                        let (message_id, event_id, artifact_sha256) = match evidence.kind {
                            bao_api::MemoryEvidenceKindV1::Message => {
                                (evidence.messageId.clone(), None, None)
                            }
                            bao_api::MemoryEvidenceKindV1::Event => (None, evidence.eventId, None),
                            bao_api::MemoryEvidenceKindV1::Artifact => {
                                (None, None, evidence.artifactSha256.clone())
                            }
                        };
                        let record = MemoryLinkRecord {
                            memory_id: link.memoryId.clone(),
                            kind: match evidence.kind {
                                bao_api::MemoryEvidenceKindV1::Message => "message".to_string(),
                                bao_api::MemoryEvidenceKindV1::Event => "event".to_string(),
                                bao_api::MemoryEvidenceKindV1::Artifact => "artifact".to_string(),
                            },
                            message_id,
                            event_id,
                            artifact_sha256,
                            weight: evidence.weight,
                            note: evidence.note.clone(),
                            created_at: ts,
                        };
                        self.storage.insert_memory_link(&record)?;
                        let _ = self.storage.insert_audit_event(
                            ts,
                            "memory.link",
                            "memory",
                            &link.memoryId,
                            &serde_json::json!({"evidence": evidence}),
                        );
                    }
                }
            }
        }
        let payload = serde_json::json!({"ok": true, "planId": plan.planId});
        append_and_load_event(
            &self.state,
            ts,
            "memory.applyMutationPlan",
            None,
            None,
            None,
            &payload,
        )
        .await
    }

    pub async fn rollback_version(
        &self,
        memory_id: String,
        version_id: String,
    ) -> Result<BaoEventV1, GatewayError> {
        let ts = now_ts();
        let version = self
            .storage
            .get_memory_version(&version_id)?
            .ok_or_else(|| {
                GatewayError::Protocol(format!("memory version not found: {version_id}"))
            })?;

        if version.memory_id != memory_id {
            return Err(GatewayError::Protocol(
                "memory/version mismatch".to_string(),
            ));
        }

        match version.op.as_str() {
            "UPSERT" => {
                let restored = restore_memory_item_from_version(&memory_id, &version, ts)?;
                self.storage.upsert_memory_item(&restored)?;
            }
            "SUPERSEDE" => {
                rollback_supersede_version(&self.storage, &memory_id, &version, ts)?;
            }
            "DELETE" => {
                let restored = restore_deleted_memory_from_version(&memory_id, &version, ts)?;
                self.storage.upsert_memory_item(&restored)?;
            }
            op => {
                return Err(GatewayError::Protocol(format!(
                    "unsupported rollback target op: {op}"
                )));
            }
        }

        let new_version = MemoryVersionRecord {
            version_id: format!("v_{}", random_token()),
            memory_id: memory_id.clone(),
            prev_version_id: Some(version_id.clone()),
            op: "ROLLBACK".to_string(),
            diff_json: serde_json::json!({"versionId": version_id, "targetOp": version.op})
                .to_string(),
            actor: "gateway".to_string(),
            created_at: ts,
        };
        self.storage.insert_memory_version(&new_version)?;
        let _ = self.storage.insert_audit_event(
            ts,
            "memory.rollback",
            "memory",
            &memory_id,
            &serde_json::json!({"versionId": version_id}),
        );

        let payload = serde_json::json!({"memoryId": memory_id, "versionId": version_id});
        append_and_load_event(
            &self.state,
            ts,
            "memory.rollbackVersion",
            None,
            None,
            None,
            &payload,
        )
        .await
    }

    pub async fn list_dimsums(&self) -> Result<BaoEventV1, GatewayError> {
        let dimsums = query_dimsums(&self.state.sqlite_path).await?;
        let payload = serde_json::json!({"dimsums": dimsums});
        append_and_load_event(
            &self.state,
            now_ts(),
            "dimsums.list",
            None,
            None,
            None,
            &payload,
        )
        .await
    }

    pub async fn enable_dimsum(&self, dimsum_id: String) -> Result<BaoEventV1, GatewayError> {
        self.set_dimsum_enabled(dimsum_id, true).await
    }

    pub async fn disable_dimsum(&self, dimsum_id: String) -> Result<BaoEventV1, GatewayError> {
        self.set_dimsum_enabled(dimsum_id, false).await
    }

    async fn set_dimsum_enabled(
        &self,
        dimsum_id: String,
        enabled: bool,
    ) -> Result<BaoEventV1, GatewayError> {
        let ts = now_ts();
        if dimsum_id.trim().is_empty() {
            return Err(GatewayError::Protocol(
                "dimsum id cannot be empty".to_string(),
            ));
        }

        if enabled {
            let trust_payload = tokio::task::spawn_blocking({
                let sqlite_path = self.state.sqlite_path.clone();
                let dimsum_id = dimsum_id.clone();
                move || {
                    let conn = Connection::open(sqlite_path)?;
                    conn.pragma_update(None, "foreign_keys", "ON")?;
                    let row: Option<(String, String, String)> = conn
                        .query_row(
                            "SELECT version, channel, manifest_json FROM dimsums WHERE dimsum_id=?1",
                            params![dimsum_id],
                            |r| Ok((r.get(0)?, r.get(1)?, r.get(2)?)),
                        )
                        .optional()?;
                    Ok::<_, GatewayError>(row)
                }
            })
            .await
            .map_err(|e| GatewayError::Protocol(format!("join: {e}")))??;

            if let Some((version, channel, manifest_json)) = trust_payload {
                let manifest: Value = serde_json::from_str(&manifest_json).map_err(|e| {
                    GatewayError::Protocol(format!(
                        "{}: manifest json parse failed for {}: {e}",
                        DIMSUM_TRUST_TAMPERED_MANIFEST, dimsum_id
                    ))
                })?;

                if let Err(err) = validate_dimsum_manifest_trust(&manifest, &dimsum_id, &channel, &version)
                {
                    let payload = serde_json::json!({
                        "code": err.code,
                        "reason": err.reason,
                        "dimsumId": dimsum_id,
                        "channel": channel,
                        "enabled": true,
                    });
                    let _ = append_and_load_event(
                        &self.state,
                        ts,
                        "dimsums.reject",
                        None,
                        None,
                        None,
                        &payload,
                    )
                    .await;
                    let _ = self.storage.insert_audit_event(
                        ts,
                        "dimsum.trust.reject",
                        "dimsum",
                        &dimsum_id,
                        &payload,
                    );
                    return Err(GatewayError::Protocol(err.protocol_message()));
                }
            }
        }

        let changed = tokio::task::spawn_blocking({
            let sqlite_path = self.state.sqlite_path.clone();
            let dimsum_id = dimsum_id.clone();
            move || {
                let conn = Connection::open(sqlite_path)?;
                conn.pragma_update(None, "foreign_keys", "ON")?;
                let changed = conn.execute(
                    "UPDATE dimsums SET enabled=?2, updated_at=?3 WHERE dimsum_id=?1",
                    params![dimsum_id, if enabled { 1 } else { 0 }, ts],
                )?;
                Ok::<_, GatewayError>(changed)
            }
        })
        .await
        .map_err(|e| GatewayError::Protocol(format!("join: {e}")))??;

        if changed == 0 {
            return Err(GatewayError::Protocol(format!(
                "dimsum not found: {dimsum_id}"
            )));
        }

        let payload = serde_json::json!({"dimsumId": dimsum_id, "enabled": enabled});
        let ty = if enabled {
            "dimsums.enable"
        } else {
            "dimsums.disable"
        };
        append_and_load_event(&self.state, ts, ty, None, None, None, &payload).await
    }

    pub async fn list_memories(&self) -> Result<BaoEventV1, GatewayError> {
        let memories = query_memories(&self.state.sqlite_path).await?;
        let payload = serde_json::json!({"memories": memories});
        append_and_load_event(
            &self.state,
            now_ts(),
            "memories.list",
            None,
            None,
            None,
            &payload,
        )
        .await
    }

    pub async fn get_settings(&self) -> Result<BaoEventV1, GatewayError> {
        let settings = query_settings(&self.state.sqlite_path).await?;
        let payload = serde_json::json!({"settings": settings});
        append_and_load_event(
            &self.state,
            now_ts(),
            "settings.get",
            None,
            None,
            None,
            &payload,
        )
        .await
    }

    /// Upsert a single setting key.
    ///
    /// Phase1: writes to `settings` table and emits a `settings.update` event.
    pub async fn update_setting(
        &self,
        key: String,
        value: Value,
    ) -> Result<BaoEventV1, GatewayError> {
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

        if key == "permissions.capabilities" {
            self.scheduler.enforce_capability_gate(ts);
        }

        let payload = serde_json::json!({"key": key, "value": value});
        append_and_load_event(
            &self.state,
            ts,
            "settings.update",
            None,
            None,
            None,
            &payload,
        )
        .await
    }

    pub async fn emit_event(
        &self,
        ty: String,
        session_id: Option<String>,
        payload: Value,
    ) -> Result<BaoEventV1, GatewayError> {
        if ty.trim().is_empty() {
            return Err(GatewayError::Protocol(
                "event type cannot be empty".to_string(),
            ));
        }
        append_and_load_event(
            &self.state,
            now_ts(),
            ty.as_str(),
            session_id.as_deref(),
            None,
            None,
            &payload,
        )
        .await
    }

    pub async fn events_since(
        &self,
        last_event_id: Option<i64>,
        limit: i64,
    ) -> Result<Vec<BaoEventV1>, GatewayError> {
        let out = tokio::task::spawn_blocking({
            let sqlite_path = self.state.sqlite_path.clone();
            move || load_events_since(&sqlite_path, last_event_id, limit)
        })
        .await
        .map_err(|e| GatewayError::Protocol(format!("join: {e}")))??;
        Ok(out)
    }

    pub async fn audit_events_since(
        &self,
        last_audit_id: Option<i64>,
        limit: i64,
    ) -> Result<Vec<AuditEventRecord>, GatewayError> {
        let out = tokio::task::spawn_blocking({
            let storage = self.storage.clone();
            move || storage.list_audit_events_since(last_audit_id, limit)
        })
        .await
        .map_err(|e| GatewayError::Protocol(format!("join: {e}")))??;
        Ok(out)
    }
}

async fn memory_search_index(
    sqlite_path: &str,
    query: &str,
    limit: i64,
) -> Result<Vec<MemoryHitV1>, GatewayError> {
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

async fn memory_get_timeline(
    sqlite_path: &str,
    namespace: Option<String>,
) -> Result<Vec<Value>, GatewayError> {
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

fn memory_record_to_json(item: &MemoryItemRecord) -> Value {
    let json_payload = item
        .json
        .as_ref()
        .and_then(|raw| serde_json::from_str::<Value>(raw).ok())
        .unwrap_or(Value::Null);

    serde_json::json!({
        "id": item.memory_id,
        "namespace": item.namespace,
        "kind": item.kind,
        "title": item.title,
        "content": item.content,
        "json": json_payload,
        "score": item.score,
        "status": item.status,
        "sourceHash": item.source_hash,
        "createdAt": item.created_at,
        "updatedAt": item.updated_at,
    })
}

fn parse_memory_item_payload(
    payload: &Value,
    fallback_memory_id: &str,
    ts: i64,
) -> Result<MemoryItemRecord, GatewayError> {
    let mem = payload
        .as_object()
        .ok_or_else(|| GatewayError::Protocol("memory payload must be object".to_string()))?;

    let memory_id = mem
        .get("id")
        .and_then(Value::as_str)
        .filter(|v| !v.trim().is_empty())
        .unwrap_or(fallback_memory_id)
        .to_string();

    let namespace = mem
        .get("namespace")
        .and_then(Value::as_str)
        .ok_or_else(|| GatewayError::Protocol("memory payload missing namespace".to_string()))?
        .to_string();
    let kind = mem
        .get("kind")
        .and_then(Value::as_str)
        .ok_or_else(|| GatewayError::Protocol("memory payload missing kind".to_string()))?
        .to_string();
    let title = mem
        .get("title")
        .and_then(Value::as_str)
        .ok_or_else(|| GatewayError::Protocol("memory payload missing title".to_string()))?
        .to_string();

    let content = mem
        .get("content")
        .and_then(Value::as_str)
        .map(ToOwned::to_owned);
    let json = mem
        .get("json")
        .and_then(|v| (!v.is_null()).then_some(v))
        .and_then(|v| serde_json::to_string(v).ok());
    let score = mem.get("score").and_then(Value::as_f64).unwrap_or(0.0);
    let status = mem
        .get("status")
        .and_then(Value::as_str)
        .unwrap_or("active")
        .to_string();
    let source_hash = mem
        .get("sourceHash")
        .and_then(Value::as_str)
        .map(ToOwned::to_owned);

    Ok(MemoryItemRecord {
        memory_id,
        namespace,
        kind,
        title,
        content,
        json,
        score,
        status,
        source_hash,
        created_at: ts,
        updated_at: ts,
        last_injected_at: None,
        inject_count: 0,
    })
}

fn restore_memory_item_from_version(
    memory_id: &str,
    version: &MemoryVersionRecord,
    ts: i64,
) -> Result<MemoryItemRecord, GatewayError> {
    let diff = serde_json::from_str::<Value>(&version.diff_json)
        .map_err(|err| GatewayError::Protocol(format!("invalid version diff json: {err}")))?;

    let mem_payload = diff
        .get("memory")
        .or_else(|| diff.get("mutation").and_then(|m| m.get("memory")))
        .ok_or_else(|| GatewayError::Protocol("version diff missing memory payload".to_string()))?;

    parse_memory_item_payload(mem_payload, memory_id, ts)
}

fn restore_deleted_memory_from_version(
    memory_id: &str,
    version: &MemoryVersionRecord,
    ts: i64,
) -> Result<MemoryItemRecord, GatewayError> {
    let diff = serde_json::from_str::<Value>(&version.diff_json)
        .map_err(|err| GatewayError::Protocol(format!("invalid version diff json: {err}")))?;

    let deleted_payload = diff
        .get("deletedMemory")
        .ok_or_else(|| GatewayError::Protocol("version diff missing deletedMemory".to_string()))?;

    parse_memory_item_payload(deleted_payload, memory_id, ts)
}

fn rollback_supersede_version(
    storage: &Storage,
    new_memory_id: &str,
    version: &MemoryVersionRecord,
    ts: i64,
) -> Result<(), GatewayError> {
    let diff = serde_json::from_str::<Value>(&version.diff_json)
        .map_err(|err| GatewayError::Protocol(format!("invalid version diff json: {err}")))?;

    let old_payload = diff
        .get("oldMemory")
        .ok_or_else(|| GatewayError::Protocol("version diff missing oldMemory".to_string()))?;

    storage.delete_memory_item(new_memory_id)?;
    let restored_old = parse_memory_item_payload(old_payload, new_memory_id, ts)?;
    storage.upsert_memory_item(&restored_old)?;

    Ok(())
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

        let storage = Arc::new(
            Storage::open(sqlite_path.clone())
                .map_err(|e| GatewayError::Protocol(e.to_string()))?,
        );
        let runner = Arc::new(ProcessToolRunner::new());
        let scheduler = Arc::new(SchedulerService::new(
            Arc::new(SqliteStorage::new(storage.clone())),
            runner,
        ));

        let state = Arc::new(GatewayState {
            sqlite_path,
            auth: AuthRegistry::new(),
            runtime_cfg: Mutex::new(RuntimeConfig { allow_lan: false }),
        });
        Ok((
            Self {
                state: state.clone(),
            },
            GatewayHandle {
                state,
                scheduler,
                storage,
            },
        ))
    }

    pub async fn start(&self, mut cfg: GatewayConfig) -> Result<(), GatewayError> {
        // Apply allow_lan override.
        let allow_lan = self
            .state
            .runtime_cfg
            .lock()
            .expect("cfg mutex poisoned")
            .allow_lan;
        cfg.bind_addr = effective_bind_addr(allow_lan);

        let addr = SocketAddr::new(cfg.bind_addr, cfg.port);
        let listener = TcpListener::bind(addr).await?;
        self.start_with_listener(listener).await
    }

    /// Start gateway with an already-bound listener.
    ///
    /// Useful for tests (bind to port 0 then read `local_addr`).
    pub async fn start_with_listener(&self, listener: TcpListener) -> Result<(), GatewayError> {
        loop {
            let (stream, peer_addr) = listener.accept().await?;
            let state = self.state.clone();
            tokio::spawn(async move {
                let _ = handle_connection(state, stream, peer_addr).await;
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

    #[serde(rename = "revokePairingToken")]
    RevokePairingToken { token: String },
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
    /// Currently connected device tokens.
    connected: Mutex<HashSet<String>>,
}

impl AuthRegistry {
    fn new() -> Self {
        Self {
            pairing: Mutex::new(HashMap::new()),
            device: Mutex::new(HashMap::new()),
            connected: Mutex::new(HashSet::new()),
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
        self.connected
            .lock()
            .expect("connected mutex poisoned")
            .remove(token);
    }

    fn accept_or_pair(&self, token: &str) -> AuthDecision {
        // Phase1 rule: token kind is explicit.
        // - p_* : one-time pairing token, returns a minted device token (d_*)
        // - d_* : long-lived device token
        if token.starts_with("d_") {
            let g = self.device.lock().expect("device mutex poisoned");
            return match g.get(token).copied() {
                Some(false) => {
                    self.connected
                        .lock()
                        .expect("connected mutex poisoned")
                        .insert(token.to_string());
                    AuthDecision::Accepted {
                        new_device_token: None,
                    }
                }
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
                    self.connected
                        .lock()
                        .expect("connected mutex poisoned")
                        .insert(device_token.clone());
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

    fn list_devices(&self) -> Vec<GatewayDevice> {
        let device = self.device.lock().expect("device mutex poisoned");
        let connected = self.connected.lock().expect("connected mutex poisoned");
        let mut out = device
            .iter()
            .filter_map(|(token, revoked)| {
                if *revoked {
                    return None;
                }
                Some(GatewayDevice {
                    device_id: token.clone(),
                    connected: connected.contains(token),
                })
            })
            .collect::<Vec<_>>();
        out.sort_by(|a, b| b.connected.cmp(&a.connected).then(a.device_id.cmp(&b.device_id)));
        out
    }

    fn set_connected(&self, token: &str, is_connected: bool) {
        if !token.starts_with("d_") {
            return;
        }
        if is_connected {
            self.connected
                .lock()
                .expect("connected mutex poisoned")
                .insert(token.to_string());
            return;
        }
        self.connected
            .lock()
            .expect("connected mutex poisoned")
            .remove(token);
    }
}

enum AuthDecision {
    Accepted { new_device_token: Option<String> },
    Rejected,
}

// -----------------------------
// Storage queries (sessions/tasks/dimsums/memories/settings/events)
// -----------------------------

fn validate_task_spec(spec: &TaskSpecV1) -> Result<(), GatewayError> {
    let mut schema = serde_json::from_str::<Value>(include_str!("../../../schemas/task_spec_v1.schema.json"))
        .map_err(|err| GatewayError::Protocol(format!("load task schema failed: {err}")))?;
    if let Some(obj) = schema.as_object_mut() {
        obj.remove("$id");
    }
    let instance = serde_json::to_value(spec)
        .map_err(|err| GatewayError::Protocol(format!("serialize task spec failed: {err}")))?;

    bao_api::validate_json_schema(&schema, &instance).map_err(|err| {
        GatewayError::Protocol(format!("task spec schema validate failed: {}", err.message))
    })?;

    validate_task_spec_business(spec)
}

fn validate_task_spec_business(spec: &TaskSpecV1) -> Result<(), GatewayError> {
    if spec.id.trim().is_empty() {
        return Err(GatewayError::Protocol("task id cannot be empty".to_string()));
    }
    if spec.title.trim().is_empty() {
        return Err(GatewayError::Protocol("task title cannot be empty".to_string()));
    }

    let tool = &spec.action.toolCall;
    if tool.dimsumId.trim().is_empty() {
        return Err(GatewayError::Protocol(
            "task action tool dimsum id cannot be empty".to_string(),
        ));
    }
    if tool.toolName.trim().is_empty() {
        return Err(GatewayError::Protocol(
            "task action tool name cannot be empty".to_string(),
        ));
    }

    match spec.schedule.kind {
        bao_api::TaskScheduleKindV1::Once => {
            if spec.schedule.runAtTs.is_none() {
                return Err(GatewayError::Protocol(
                    "schedule.once requires runAtTs".to_string(),
                ));
            }
        }
        bao_api::TaskScheduleKindV1::Interval => {
            let ms = spec.schedule.intervalMs.ok_or_else(|| {
                GatewayError::Protocol("schedule.interval requires intervalMs".to_string())
            })?;
            if ms < 1000 {
                return Err(GatewayError::Protocol(
                    "schedule.intervalMs must be >= 1000".to_string(),
                ));
            }
        }
        bao_api::TaskScheduleKindV1::Cron => {
            let cron_expr = spec
                .schedule
                .cron
                .as_deref()
                .map(str::trim)
                .filter(|v| !v.is_empty())
                .ok_or_else(|| GatewayError::Protocol("schedule.cron requires cron".to_string()))?;

            Schedule::from_str(cron_expr).map_err(|err| {
                GatewayError::Protocol(format!("invalid schedule.cron expression: {err}"))
            })?;

            if let Some(tz) = spec
                .schedule
                .timezone
                .as_deref()
                .map(str::trim)
                .filter(|v| !v.is_empty())
            {
                tz.parse::<Tz>()
                    .map_err(|err| GatewayError::Protocol(format!("invalid schedule.timezone: {err}")))?;
            }
        }
    }

    if let Some(policy) = spec.policy.as_ref() {
        if let Some(max_retries) = policy.maxRetries {
            if !(0..=1).contains(&max_retries) {
                return Err(GatewayError::Protocol(
                    "policy.maxRetries must be between 0 and 1".to_string(),
                ));
            }
        }
        if let Some(timeout_ms) = policy.timeoutMs {
            if timeout_ms < 1 {
                return Err(GatewayError::Protocol(
                    "policy.timeoutMs must be >= 1".to_string(),
                ));
            }
        }
    }

    Ok(())
}

fn now_ts() -> i64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or(Duration::from_secs(0))
        .as_secs() as i64
}

fn random_token() -> String {
    let mut bytes = [0u8; 16];
    OsRng.fill_bytes(&mut bytes);
    hex::encode(bytes)
}

fn load_events_since(
    sqlite_path: &str,
    last_event_id: Option<i64>,
    limit: i64,
) -> Result<Vec<BaoEventV1>, GatewayError> {
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

    seed_bundled_dimsums(&conn, sqlite_path)?;
    seed_default_session(&conn)?;
    seed_default_settings(&conn)?;
    Ok(())
}

fn seed_default_session(conn: &Connection) -> Result<(), GatewayError> {
    let now = now_ts();
    conn.execute(
        "INSERT INTO sessions(session_id, title, created_at, updated_at) VALUES (?1, ?2, ?3, ?3) \
         ON CONFLICT(session_id) DO NOTHING",
        params!["default", "Default Session", now],
    )?;
    Ok(())
}

fn seed_default_settings(conn: &Connection) -> Result<(), GatewayError> {
    let now = now_ts();
    let defaults = [
        ("gateway.allowLan", serde_json::json!(false)),
        ("gateway.running", serde_json::json!(false)),
        ("provider.active", serde_json::json!("openai")),
        ("provider.model", serde_json::json!("gpt-4.1-mini")),
        (
            "provider.baseUrl",
            serde_json::json!("https://api.openai.com/v1"),
        ),
    ];

    for (key, value) in defaults {
        conn.execute(
            "INSERT INTO settings(key, value_json, updated_at) VALUES (?1, ?2, ?3) \
             ON CONFLICT(key) DO NOTHING",
            params![key, value.to_string(), now],
        )?;
    }

    Ok(())
}

fn seed_bundled_dimsums(conn: &Connection, sqlite_path: &str) -> Result<(), GatewayError> {
    let root = bundled_dimsums_root()?;
    let now = now_ts();

    conn.execute_batch("BEGIN IMMEDIATE")?;
    let mut upsert_count = 0_usize;

    let run_result: Result<(), BundledUpgradeFailure> = (|| {
        for entry in fs::read_dir(root)
            .map_err(|e| BundledUpgradeFailure {
                code: DIMSUM_UPGRADE_FAILED_ROLLBACK_APPLIED,
                reason: format!("read dimsums dir failed: {e}"),
                dimsum_id: "bundled".to_string(),
                channel: None,
                manifest_path: None,
                installed_version: None,
                incoming_version: None,
            })?
        {
            let entry = entry.map_err(|e| BundledUpgradeFailure {
                code: DIMSUM_UPGRADE_FAILED_ROLLBACK_APPLIED,
                reason: format!("read dimsums entry failed: {e}"),
                dimsum_id: "bundled".to_string(),
                channel: None,
                manifest_path: None,
                installed_version: None,
                incoming_version: None,
            })?;
            let path = entry.path();
            if !path.is_dir() {
                continue;
            }
            let manifest_path = path.join("manifest.json");
            if !manifest_path.exists() {
                continue;
            }

            let manifest_text = fs::read_to_string(&manifest_path).map_err(|e| BundledUpgradeFailure {
                code: DIMSUM_UPGRADE_FAILED_ROLLBACK_APPLIED,
                reason: format!("read manifest failed ({:?}): {e}", manifest_path),
                dimsum_id: "bundled".to_string(),
                channel: None,
                manifest_path: Some(manifest_path.to_string_lossy().to_string()),
                installed_version: None,
                incoming_version: None,
            })?;
            let mut manifest_json: Value = serde_json::from_str(&manifest_text).map_err(|e| BundledUpgradeFailure {
                code: DIMSUM_TRUST_TAMPERED_MANIFEST,
                reason: format!("parse manifest failed ({:?}): {e}", manifest_path),
                dimsum_id: "bundled".to_string(),
                channel: None,
                manifest_path: Some(manifest_path.to_string_lossy().to_string()),
                installed_version: None,
                incoming_version: None,
            })?;

            let dimsum_id = manifest_json
                .get("id")
                .and_then(Value::as_str)
                .ok_or_else(|| BundledUpgradeFailure {
                    code: DIMSUM_TRUST_TAMPERED_MANIFEST,
                    reason: format!("manifest missing id ({:?})", manifest_path),
                    dimsum_id: "bundled".to_string(),
                    channel: None,
                    manifest_path: Some(manifest_path.to_string_lossy().to_string()),
                    installed_version: None,
                    incoming_version: None,
                })?
                .to_string();
            let version = manifest_json
                .get("version")
                .and_then(Value::as_str)
                .unwrap_or("0.0.0")
                .to_string();

            normalize_legacy_bundled_signature(&mut manifest_json, &dimsum_id, &version).map_err(
                |e| BundledUpgradeFailure {
                    code: DIMSUM_TRUST_TAMPERED_MANIFEST,
                    reason: e.to_string(),
                    dimsum_id: dimsum_id.clone(),
                    channel: None,
                    manifest_path: Some(manifest_path.to_string_lossy().to_string()),
                    installed_version: None,
                    incoming_version: Some(version.clone()),
                },
            )?;

            let channel = manifest_json
                .get("distribution")
                .and_then(|d| d.get("channel"))
                .and_then(Value::as_str)
                .unwrap_or("bundled")
                .to_string();

            if let Err(err) =
                validate_dimsum_manifest_trust(&manifest_json, &dimsum_id, &channel, &version)
            {
                return Err(BundledUpgradeFailure {
                    code: err.code,
                    reason: err.reason,
                    dimsum_id,
                    channel: Some(channel),
                    manifest_path: Some(manifest_path.to_string_lossy().to_string()),
                    installed_version: None,
                    incoming_version: Some(version),
                });
            }

            let existing_version: Option<String> = conn
                .query_row(
                    "SELECT version FROM dimsums WHERE dimsum_id=?1",
                    params![dimsum_id],
                    |r| r.get(0),
                )
                .optional()
                .map_err(|e| BundledUpgradeFailure {
                    code: DIMSUM_UPGRADE_FAILED_ROLLBACK_APPLIED,
                    reason: e.to_string(),
                    dimsum_id: dimsum_id.clone(),
                    channel: Some(channel.clone()),
                    manifest_path: Some(manifest_path.to_string_lossy().to_string()),
                    installed_version: None,
                    incoming_version: Some(version.clone()),
                })?;

            if let Some(existing) = existing_version {
                if compare_semver(&existing, &version).is_gt() {
                    return Err(BundledUpgradeFailure {
                        code: DIMSUM_TRUST_DOWNGRADE_BLOCKED,
                        reason: format!(
                            "downgrade blocked for {}: installed={}, incoming={}",
                            dimsum_id, existing, version
                        ),
                        dimsum_id,
                        channel: Some(channel),
                        manifest_path: Some(manifest_path.to_string_lossy().to_string()),
                        installed_version: Some(existing),
                        incoming_version: Some(version),
                    });
                }
            }

            let manifest_text = serde_json::to_string(&manifest_json).map_err(|e| {
                BundledUpgradeFailure {
                    code: DIMSUM_TRUST_TAMPERED_MANIFEST,
                    reason: format!("serialize manifest failed ({:?}): {e}", manifest_path),
                    dimsum_id: dimsum_id.clone(),
                    channel: Some(channel.clone()),
                    manifest_path: Some(manifest_path.to_string_lossy().to_string()),
                    installed_version: None,
                    incoming_version: Some(version.clone()),
                }
            })?;

            conn.execute(
                "INSERT INTO dimsums(dimsum_id, enabled, channel, version, manifest_json, installed_at, updated_at) \
                 VALUES (?1, 1, 'bundled', ?2, ?3, ?4, ?4) \
                 ON CONFLICT(dimsum_id) DO UPDATE SET version=excluded.version, manifest_json=excluded.manifest_json, updated_at=excluded.updated_at",
                params![dimsum_id, version, manifest_text, now],
            )
            .map_err(|e| BundledUpgradeFailure {
                code: DIMSUM_UPGRADE_FAILED_ROLLBACK_APPLIED,
                reason: e.to_string(),
                dimsum_id: "bundled".to_string(),
                channel: None,
                manifest_path: Some(manifest_path.to_string_lossy().to_string()),
                installed_version: None,
                incoming_version: None,
            })?;

            upsert_count += 1;
            if should_inject_upgrade_failpoint(conn, upsert_count) {
                return Err(BundledUpgradeFailure {
                    code: DIMSUM_UPGRADE_FAILED_ROLLBACK_APPLIED,
                    reason: "injected bundled upgrade failure by test failpoint".to_string(),
                    dimsum_id: "bundled".to_string(),
                    channel: Some("bundled".to_string()),
                    manifest_path: Some(manifest_path.to_string_lossy().to_string()),
                    installed_version: None,
                    incoming_version: None,
                });
            }
        }

        Ok(())
    })();

    if let Err(err) = run_result {
        let _ = conn.execute_batch("ROLLBACK");
        record_upgrade_failure_events(sqlite_path, now, &err);
        return Err(GatewayError::Protocol(format!(
            "{}: failedCode={}, dimsumId={}, reason={}",
            DIMSUM_UPGRADE_FAILED_ROLLBACK_APPLIED, err.code, err.dimsum_id, err.reason
        )));
    }

    conn.execute_batch("COMMIT")?;
    Ok(())
}

fn should_inject_upgrade_failpoint(conn: &Connection, upsert_count: usize) -> bool {
    let target = conn
        .query_row(
            "SELECT value_json FROM settings WHERE key='__test.failBundledUpgradeAfter'",
            [],
            |r| r.get::<_, String>(0),
        )
        .optional()
        .ok()
        .flatten()
        .and_then(|raw| serde_json::from_str::<Value>(&raw).ok())
        .and_then(|v| v.as_u64())
        .unwrap_or(0);
    target > 0 && (upsert_count as u64) >= target
}

fn record_upgrade_failure_events(sqlite_path: &str, ts: i64, failure: &BundledUpgradeFailure) {
    let reject_payload = serde_json::json!({
        "code": failure.code,
        "reason": failure.reason,
        "dimsumId": failure.dimsum_id,
        "channel": failure.channel,
        "path": failure.manifest_path,
        "installedVersion": failure.installed_version,
        "incomingVersion": failure.incoming_version,
    });
    let rollback_payload = serde_json::json!({
        "code": DIMSUM_UPGRADE_FAILED_ROLLBACK_APPLIED,
        "failedCode": failure.code,
        "reason": failure.reason,
        "dimsumId": failure.dimsum_id,
        "channel": failure.channel,
        "path": failure.manifest_path,
        "installedVersion": failure.installed_version,
        "incomingVersion": failure.incoming_version,
        "rolledBack": true,
    });

    let Ok(storage) = Storage::open_unchecked(sqlite_path.to_string()) else {
        return;
    };

    let _ = storage.insert_event(ts, "dimsums.upgrade.rollback", None, None, None, &rollback_payload);
    let _ = storage.insert_audit_event(
        ts,
        "dimsum.upgrade.rollback",
        "dimsum",
        &failure.dimsum_id,
        &rollback_payload,
    );
    let _ = storage.insert_audit_event(ts, "dimsum.install.reject", "dimsum", &failure.dimsum_id, &reject_payload);
}

fn bundled_dimsums_root() -> Result<std::path::PathBuf, GatewayError> {
    let manifest_dir = std::path::Path::new(env!("CARGO_MANIFEST_DIR"));
    let root = manifest_dir.join("../../dimsums/bundled");
    if root.exists() {
        return Ok(root);
    }
    Err(GatewayError::Protocol(format!(
        "bundled dimsums directory not found: {}",
        root.to_string_lossy()
    )))
}

fn trusted_signer_for_channel(channel: &str) -> Option<&'static str> {
    match channel {
        "bundled" => Some(TRUSTED_SIGNER_BUNDLED),
        "community" => Some(TRUSTED_SIGNER_COMMUNITY),
        _ => None,
    }
}

fn normalize_legacy_bundled_signature(
    manifest: &mut Value,
    dimsum_id: &str,
    version: &str,
) -> Result<(), GatewayError> {
    let Some(root) = manifest.as_object_mut() else {
        return Err(GatewayError::Protocol("manifest root must be object".to_string()));
    };
    let Some(distribution) = root.get_mut("distribution").and_then(Value::as_object_mut) else {
        return Ok(());
    };
    let channel = distribution
        .get("channel")
        .and_then(Value::as_str)
        .unwrap_or_default()
        .to_string();
    if channel != "bundled" {
        return Ok(());
    }
    let Some(integrity) = distribution.get_mut("integrity").and_then(Value::as_object_mut) else {
        return Ok(());
    };
        let sha256 = integrity
            .get("sha256")
            .and_then(Value::as_str)
            .unwrap_or("0000000000000000000000000000000000000000000000000000000000000000")
            .to_string();
    if integrity
        .get("signedBy")
        .and_then(Value::as_str)
        .unwrap_or("")
        .is_empty()
    {
        integrity.insert(
            "signedBy".to_string(),
            Value::String(TRUSTED_SIGNER_BUNDLED.to_string()),
        );
    }
    if integrity
        .get("signature")
        .and_then(Value::as_str)
        .unwrap_or("")
        .is_empty()
    {
        let signature = expected_signature(
            dimsum_id,
            version,
            &sha256,
            TRUSTED_SIGNER_BUNDLED,
        );
        integrity.insert("signature".to_string(), Value::String(signature));
    }
    Ok(())
}

fn validate_dimsum_manifest_trust(
    manifest: &Value,
    expected_dimsum_id: &str,
    expected_channel: &str,
    expected_version: &str,
) -> Result<(), DimsumTrustError> {
    let manifest_id = manifest
        .get("id")
        .and_then(Value::as_str)
        .ok_or_else(|| DimsumTrustError {
            code: DIMSUM_TRUST_TAMPERED_MANIFEST,
            reason: "manifest.id is missing".to_string(),
        })?;
    if manifest_id != expected_dimsum_id {
        return Err(DimsumTrustError {
            code: DIMSUM_TRUST_TAMPERED_MANIFEST,
            reason: format!(
                "manifest id mismatch (expected={}, got={})",
                expected_dimsum_id, manifest_id
            ),
        });
    }

    let manifest_version = manifest
        .get("version")
        .and_then(Value::as_str)
        .ok_or_else(|| DimsumTrustError {
            code: DIMSUM_TRUST_TAMPERED_MANIFEST,
            reason: "manifest.version is missing".to_string(),
        })?;
    if manifest_version != expected_version {
        return Err(DimsumTrustError {
            code: DIMSUM_TRUST_TAMPERED_MANIFEST,
            reason: format!(
                "manifest version mismatch (expected={}, got={})",
                expected_version, manifest_version
            ),
        });
    }

    let distribution = manifest
        .get("distribution")
        .and_then(Value::as_object)
        .ok_or_else(|| DimsumTrustError {
            code: DIMSUM_TRUST_TAMPERED_MANIFEST,
            reason: "distribution is missing".to_string(),
        })?;
    let channel = distribution
        .get("channel")
        .and_then(Value::as_str)
        .ok_or_else(|| DimsumTrustError {
            code: DIMSUM_TRUST_TAMPERED_MANIFEST,
            reason: "distribution.channel is missing".to_string(),
        })?;
    if channel != expected_channel {
        return Err(DimsumTrustError {
            code: DIMSUM_TRUST_TAMPERED_MANIFEST,
            reason: format!(
                "manifest channel mismatch (expected={}, got={})",
                expected_channel, channel
            ),
        });
    }

    let trusted_signer = trusted_signer_for_channel(channel).ok_or_else(|| DimsumTrustError {
        code: DIMSUM_TRUST_UNTRUSTED_SOURCE,
        reason: format!("untrusted channel: {channel}"),
    })?;

    let integrity = distribution
        .get("integrity")
        .and_then(Value::as_object)
        .ok_or_else(|| DimsumTrustError {
            code: DIMSUM_TRUST_TAMPERED_MANIFEST,
            reason: "distribution.integrity is missing".to_string(),
        })?;
    let sha256 = integrity
        .get("sha256")
        .and_then(Value::as_str)
        .ok_or_else(|| DimsumTrustError {
            code: DIMSUM_TRUST_TAMPERED_MANIFEST,
            reason: "integrity.sha256 is missing".to_string(),
        })?;
    if sha256.len() != 64 {
        return Err(DimsumTrustError {
            code: DIMSUM_TRUST_TAMPERED_MANIFEST,
            reason: format!("integrity.sha256 must be 64 chars, got {}", sha256.len()),
        });
    }

    let signed_by = integrity
        .get("signedBy")
        .and_then(Value::as_str)
        .ok_or_else(|| DimsumTrustError {
            code: DIMSUM_TRUST_INVALID_SIGNATURE,
            reason: "integrity.signedBy is missing".to_string(),
        })?;
    if signed_by != trusted_signer {
        return Err(DimsumTrustError {
            code: DIMSUM_TRUST_UNTRUSTED_SOURCE,
            reason: format!("signer {} is not trusted for channel {}", signed_by, channel),
        });
    }

    let signature = integrity
        .get("signature")
        .and_then(Value::as_str)
        .ok_or_else(|| DimsumTrustError {
            code: DIMSUM_TRUST_INVALID_SIGNATURE,
            reason: "integrity.signature is missing".to_string(),
        })?;
    let expected_sig = expected_signature(manifest_id, manifest_version, sha256, signed_by);
    if signature != expected_sig {
        return Err(DimsumTrustError {
            code: DIMSUM_TRUST_INVALID_SIGNATURE,
            reason: "signature mismatch".to_string(),
        });
    }

    Ok(())
}

fn expected_signature(dimsum_id: &str, version: &str, sha256: &str, signed_by: &str) -> String {
    format!(
        "bao.sig.v1:{}:{}:{}:{}",
        dimsum_id, version, sha256, signed_by
    )
}

fn compare_semver(left: &str, right: &str) -> std::cmp::Ordering {
    let left_parts = parse_semver_core(left);
    let right_parts = parse_semver_core(right);
    left_parts.cmp(&right_parts)
}

fn parse_semver_core(version: &str) -> (u64, u64, u64) {
    let core = version.split('-').next().unwrap_or(version);
    let mut parts = core.split('.');
    let major = parts.next().unwrap_or("0").parse::<u64>().unwrap_or(0);
    let minor = parts.next().unwrap_or("0").parse::<u64>().unwrap_or(0);
    let patch = parts.next().unwrap_or("0").parse::<u64>().unwrap_or(0);
    (major, minor, patch)
}

// -----------------------------
// Minimal WebSocket-over-TCP implementation
// -----------------------------

// NOTE: This is a minimal, self-contained WS implementation sufficient for tests.
// - Text frames only
// - Client->server must be masked (RFC6455); we enforce and unmask
// - Server->client is unmasked
// - No fragmentation

async fn handle_connection(
    state: Arc<GatewayState>,
    mut stream: TcpStream,
    peer_addr: SocketAddr,
) -> Result<(), GatewayError> {
    reject_source_if_needed(&state, peer_addr.ip()).await?;

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

    let key = parse_ws_key(&req).ok_or(GatewayError::Handshake(
        "missing sec-websocket-key".to_string(),
    ))?;
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
        ClientFrameV1::Hello {
            token,
            last_event_id,
        } => (token, last_event_id),
        _ => {
            return Err(GatewayError::Protocol("first frame not hello".to_string()));
        }
    };

    let auth = state.auth.accept_or_pair(&token);
    let new_device_token = match auth {
        AuthDecision::Accepted { new_device_token } => new_device_token,
        AuthDecision::Rejected => return Err(GatewayError::Unauthorized),
    };

    let storage = Storage::open(state.sqlite_path.clone())
        .map_err(|e| GatewayError::Protocol(e.to_string()))?;

    // If this connection was established via pairing token, mint a device token and send it
    // back as a BaoEventV1. (Phase1: stored in-memory only.)
    // NOTE: For minimal correctness with lastEventId semantics, we persist this event.
    let mut paired_event_id: Option<i64> = None;
    if token.starts_with("p_") {
        if let Some(device_token) = new_device_token.clone() {
            let payload = serde_json::json!({"token": device_token});
            let evt =
                append_and_load_event(&state, now_ts(), "auth.paired", None, None, None, &payload)
                    .await?;
            paired_event_id = Some(evt.eventId);
            let _ = storage
                .insert_audit_event(now_ts(), "auth.pairing.accept", "auth", "pairing", &payload)
                .map_err(|e| GatewayError::Protocol(e.to_string()))?;
            let _ = storage
                .insert_audit_event(now_ts(), "auth.device.issued", "auth", "device", &payload)
                .map_err(|e| GatewayError::Protocol(e.to_string()))?;
            let txt = serde_json::to_string(&evt).unwrap();
            write_ws_text_frame(&mut stream, &txt).await?;
        }
    }

    let active_device_token = if token.starts_with("d_") {
        Some(token.clone())
    } else {
        new_device_token.clone()
    };

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

    let mut exit_result: Result<(), GatewayError> = Ok(());
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
                    Err(GatewayError::Io(e)) if e.kind() == std::io::ErrorKind::UnexpectedEof => {
                        exit_result = Ok(());
                        break;
                    }
                    Err(e) => {
                        exit_result = Err(e);
                        break;
                    }
                };
                let frame: ClientFrameV1 = match serde_json::from_str(&txt) {
                    Ok(frame) => frame,
                    Err(e) => {
                        exit_result = Err(GatewayError::Protocol(format!("invalid frame json: {e}")));
                        break;
                    }
                };
                let evt = match handle_client_command(&state, frame).await {
                    Ok(evt) => evt,
                    Err(e) => {
                        exit_result = Err(e);
                        break;
                    }
                };
                cursor = cursor.max(evt.eventId);
                let out = serde_json::to_string(&evt).unwrap();
                if let Err(e) = write_ws_text_frame(&mut stream, &out).await {
                    exit_result = Err(e);
                    break;
                }
            }
        }
    }

    if let Some(device_token) = active_device_token.as_deref() {
        state.auth.set_connected(device_token, false);
    }

    exit_result
}

fn effective_bind_addr(allow_lan: bool) -> IpAddr {
    if allow_lan {
        IpAddr::V4(Ipv4Addr::UNSPECIFIED)
    } else {
        IpAddr::V4(Ipv4Addr::LOCALHOST)
    }
}

fn is_source_ip_allowed(source_ip: IpAddr, allow_lan: bool) -> bool {
    if source_ip.is_loopback() {
        return true;
    }
    if !allow_lan {
        return false;
    }

    match source_ip {
        IpAddr::V4(ip) => {
            let octets = ip.octets();
            let is_rfc1918 = octets[0] == 10
                || (octets[0] == 172 && (16..=31).contains(&octets[1]))
                || (octets[0] == 192 && octets[1] == 168);
            let is_tailscale = octets[0] == 100 && (64..=127).contains(&octets[1]);
            is_rfc1918 || is_tailscale
        }
        IpAddr::V6(_) => false,
    }
}

async fn reject_source_if_needed(
    state: &Arc<GatewayState>,
    source_ip: IpAddr,
) -> Result<(), GatewayError> {
    let allow_lan = state
        .runtime_cfg
        .lock()
        .expect("cfg mutex poisoned")
        .allow_lan;
    if is_source_ip_allowed(source_ip, allow_lan) {
        return Ok(());
    }

    let ts = now_ts();
    let payload = serde_json::json!({
        "code": GATEWAY_SOURCE_PUBLIC_REJECTED,
        "reason": "public source is blocked; only RFC1918 LAN and Tailscale are allowed",
        "sourceIp": source_ip.to_string(),
        "allowLan": allow_lan,
    });
    let _ = append_and_load_event(
        state,
        ts,
        "gateway.connection.reject",
        None,
        None,
        None,
        &payload,
    )
    .await?;
    let _ = Storage::open(state.sqlite_path.clone())
        .map_err(|e| GatewayError::Protocol(e.to_string()))?
        .insert_audit_event(ts, "gateway.connection.reject", "gateway", "connection", &payload)
        .map_err(|e| GatewayError::Protocol(e.to_string()))?;
    Err(GatewayError::Unauthorized)
}

async fn handle_client_command(
    state: &GatewayState,
    frame: ClientFrameV1,
) -> Result<BaoEventV1, GatewayError> {
    let ts = now_ts();
    match frame {
        ClientFrameV1::Hello { .. } => Err(GatewayError::Protocol("duplicate hello".to_string())),
        ClientFrameV1::SendMessage { session_id, text } => {
            ensure_session_exists(&state.sqlite_path, &session_id, ts).await?;
            let payload = serde_json::json!({"sessionId": session_id, "text": text});
            append_and_load_event(
                state,
                ts,
                "message.send",
                Some(&session_id),
                None,
                None,
                &payload,
            )
            .await
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
        ClientFrameV1::RevokePairingToken { token } => {
            state.auth.revoke(&token);
            let payload = serde_json::json!({"token": token});
            let _ = Storage::open(state.sqlite_path.clone())
                .map_err(|e| GatewayError::Protocol(e.to_string()))?
                .insert_audit_event(ts, "auth.pairing.revoke", "auth", "pairing", &payload)
                .map_err(|e| GatewayError::Protocol(e.to_string()))?;
            append_and_load_event(
                state,
                ts,
                "auth.pairing.revoked",
                None,
                None,
                None,
                &payload,
            )
            .await
        }
    }
}

async fn ensure_session_exists(
    sqlite_path: &str,
    session_id: &str,
    ts: i64,
) -> Result<(), GatewayError> {
    let sqlite_path = sqlite_path.to_string();
    let session_id = session_id.to_string();
    tokio::task::spawn_blocking(move || {
        let conn = Connection::open(sqlite_path)?;
        conn.pragma_update(None, "foreign_keys", "ON")?;
        conn.execute(
            "INSERT INTO sessions(session_id, title, created_at, updated_at) VALUES (?1, ?2, ?3, ?3) \
             ON CONFLICT(session_id) DO UPDATE SET updated_at=excluded.updated_at",
            params![session_id.clone(), session_id, ts],
        )?;
        Ok::<_, GatewayError>(())
    })
    .await
    .map_err(|e| GatewayError::Protocol(format!("join: {e}")))??;
    Ok(())
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

async fn write_http_json(
    stream: &mut TcpStream,
    status: u16,
    body: Value,
) -> Result<(), GatewayError> {
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
        let mut stmt =
            conn.prepare("SELECT key, value_json, updated_at FROM settings ORDER BY key ASC")?;
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
        return Err(GatewayError::Protocol(
            "fragmented frames not supported".to_string(),
        ));
    }
    if opcode == 0x8 {
        return Err(GatewayError::Protocol("close".to_string()));
    }
    if opcode != 0x1 {
        return Err(GatewayError::Protocol(
            "only text frames supported".to_string(),
        ));
    }

    let masked = (hdr[1] & 0x80) != 0;
    if !masked {
        return Err(GatewayError::Protocol(
            "client frames must be masked".to_string(),
        ));
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
    use tempfile::TempDir;
    use tokio::net::TcpStream;

    #[derive(Debug, Deserialize)]
    struct TestBaoEventV1 {
        #[serde(rename = "eventId")]
        event_id: i64,
        #[allow(dead_code)]
        ts: i64,
        #[serde(rename = "type")]
        ty: String,
        #[serde(rename = "sessionId")]
        #[allow(dead_code)]
        session_id: Option<String>,
        #[serde(rename = "messageId")]
        #[allow(dead_code)]
        message_id: Option<String>,
        #[serde(rename = "deviceId")]
        #[allow(dead_code)]
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
            return Err(GatewayError::Handshake(format!(
                "unexpected response: {txt}"
            )));
        }
        Ok(s)
    }

    async fn write_masked_text_frame(
        stream: &mut TcpStream,
        text: &str,
    ) -> Result<(), GatewayError> {
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
            return Err(GatewayError::Protocol(
                "fragmented frames not supported".to_string(),
            ));
        }
        if opcode != 0x1 {
            return Err(GatewayError::Protocol("expected text frame".to_string()));
        }
        let masked = (hdr[1] & 0x80) != 0;
        if masked {
            return Err(GatewayError::Protocol(
                "server frames must be unmasked".to_string(),
            ));
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

        let listener = TcpListener::bind((Ipv4Addr::LOCALHOST, 0))
            .await
            .expect("bind");
        let addr = listener.local_addr().expect("local_addr");
        let jh = tokio::spawn(async move { server.start_with_listener(listener).await });

        let mut ws = ws_handshake(addr).await.expect("handshake");
        let hello = serde_json::json!({"type": "hello", "token": "nope", "lastEventId": null});
        write_masked_text_frame(&mut ws, &hello.to_string())
            .await
            .expect("write");

        let r = time::timeout(
            Duration::from_millis(300),
            read_unmasked_text_frame(&mut ws),
        )
        .await;
        assert!(
            r.is_err() || r.unwrap().is_err(),
            "expected connection drop"
        );

        jh.abort();
    }

    #[tokio::test]
    async fn reconnect_replays_events_after_last_event_id() {
        let (_dir, sqlite_path) = temp_sqlite_path();
        let (server, handle) = GatewayServer::open(sqlite_path).expect("open");

        let listener = TcpListener::bind((Ipv4Addr::LOCALHOST, 0))
            .await
            .expect("bind");
        let addr = listener.local_addr().expect("local_addr");
        let jh = tokio::spawn(async move { server.start_with_listener(listener).await });

        let pairing = handle.create_pairing_token();

        // first connection: pair
        let mut ws1 = ws_handshake(addr).await.expect("handshake1");
        let hello1 = serde_json::json!({"type": "hello", "token": pairing, "lastEventId": null});
        write_masked_text_frame(&mut ws1, &hello1.to_string())
            .await
            .expect("write hello1");

        // auth.paired should come first
        let paired_txt = read_unmasked_text_frame(&mut ws1)
            .await
            .expect("read paired");
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
        write_masked_text_frame(&mut ws1, &cmd.to_string())
            .await
            .expect("write sendMessage");
        let msg_txt = read_unmasked_text_frame(&mut ws1).await.expect("read msg");
        let msg_evt: TestBaoEventV1 = serde_json::from_str(&msg_txt).expect("parse msg");
        assert_eq!(msg_evt.ty, "message.send");
        assert!(msg_evt.event_id > paired_evt.event_id);

        drop(ws1);

        // reconnect with lastEventId = paired event id, should replay message.send
        let mut ws2 = ws_handshake(addr).await.expect("handshake2");
        let hello2 = serde_json::json!({"type": "hello", "token": device_token, "lastEventId": paired_evt.event_id});
        write_masked_text_frame(&mut ws2, &hello2.to_string())
            .await
            .expect("write hello2");

        let replay_txt = time::timeout(Duration::from_secs(1), read_unmasked_text_frame(&mut ws2))
            .await
            .expect("timeout")
            .expect("read replay");
        let replay_evt: TestBaoEventV1 = serde_json::from_str(&replay_txt).expect("parse replay");
        assert_eq!(replay_evt.ty, "message.send");
        assert_eq!(replay_evt.event_id, msg_evt.event_id);

        jh.abort();
    }

    #[tokio::test]
    async fn audit_events_since_should_support_cursor_and_limit() {
        let (_dir, sqlite_path) = temp_sqlite_path();
        let (_server, handle) = GatewayServer::open(sqlite_path).expect("open");

        let _ = handle.create_pairing_token();
        let _ = handle.create_pairing_token();

        let first_page = handle
            .audit_events_since(None, 1)
            .await
            .expect("first page");
        assert_eq!(first_page.len(), 1);
        assert_eq!(first_page[0].action, "auth.pairing.create");

        let cursor = first_page[0].id;
        let second_page = handle
            .audit_events_since(Some(cursor), 10)
            .await
            .expect("second page");
        assert!(!second_page.is_empty());
        assert!(second_page.iter().all(|item| item.id > cursor));
        assert!(second_page
            .iter()
            .all(|item| item.action == "auth.pairing.create"));
    }

    #[test]
    fn allow_lan_false_should_bind_localhost_only() {
        assert_eq!(
            effective_bind_addr(false),
            IpAddr::V4(Ipv4Addr::LOCALHOST)
        );
    }

    #[test]
    fn allow_lan_true_should_bind_unspecified() {
        assert_eq!(
            effective_bind_addr(true),
            IpAddr::V4(Ipv4Addr::UNSPECIFIED)
        );
    }

    #[test]
    fn source_boundary_should_allow_lan_tailscale_and_loopback() {
        assert!(is_source_ip_allowed(
            IpAddr::V4(Ipv4Addr::new(10, 9, 8, 7)),
            true
        ));
        assert!(is_source_ip_allowed(
            IpAddr::V4(Ipv4Addr::new(172, 16, 0, 1)),
            true
        ));
        assert!(is_source_ip_allowed(
            IpAddr::V4(Ipv4Addr::new(192, 168, 10, 20)),
            true
        ));
        assert!(is_source_ip_allowed(
            IpAddr::V4(Ipv4Addr::new(100, 64, 10, 20)),
            true
        ));
        assert!(is_source_ip_allowed(
            IpAddr::V4(Ipv4Addr::LOCALHOST),
            true
        ));
        assert!(is_source_ip_allowed(IpAddr::V6(std::net::Ipv6Addr::LOCALHOST), true));
    }

    #[test]
    fn source_boundary_should_reject_public_addresses() {
        assert!(!is_source_ip_allowed(
            IpAddr::V4(Ipv4Addr::new(8, 8, 8, 8)),
            true
        ));
        assert!(!is_source_ip_allowed(
            IpAddr::V4(Ipv4Addr::new(1, 1, 1, 1)),
            true
        ));
        assert!(!is_source_ip_allowed(
            IpAddr::V6(std::net::Ipv6Addr::new(0x2001, 0xdb8, 0, 0, 0, 0, 0, 1)),
            true
        ));
    }

    #[tokio::test]
    async fn public_source_reject_should_write_event_and_audit() {
        let (_dir, sqlite_path) = temp_sqlite_path();
        init_sqlite(&sqlite_path).expect("init sqlite");
        let state = Arc::new(GatewayState {
            sqlite_path: sqlite_path.clone(),
            auth: AuthRegistry::new(),
            runtime_cfg: Mutex::new(RuntimeConfig { allow_lan: true }),
        });

        let res = reject_source_if_needed(&state, IpAddr::V4(Ipv4Addr::new(8, 8, 8, 8))).await;
        assert!(matches!(res, Err(GatewayError::Unauthorized)));

        let conn = Connection::open(sqlite_path).expect("open sqlite");
        let (event_type, payload_json): (String, String) = conn
            .query_row(
                "SELECT type, payload_json FROM events ORDER BY eventId DESC LIMIT 1",
                [],
                |r| Ok((r.get(0)?, r.get(1)?)),
            )
            .expect("query event");
        assert_eq!(event_type, "gateway.connection.reject");
        let payload: serde_json::Value = serde_json::from_str(&payload_json).expect("parse payload");
        assert_eq!(payload["code"], "GATEWAY_SOURCE_PUBLIC_REJECTED");

        let (action, audit_payload_json): (String, String) = conn
            .query_row(
                "SELECT action, payload_json FROM audit_events ORDER BY id DESC LIMIT 1",
                [],
                |r| Ok((r.get(0)?, r.get(1)?)),
            )
            .expect("query audit");
        assert_eq!(action, "gateway.connection.reject");
        let audit_payload: serde_json::Value =
            serde_json::from_str(&audit_payload_json).expect("parse audit payload");
        assert_eq!(audit_payload["code"], "GATEWAY_SOURCE_PUBLIC_REJECTED");
    }

    #[test]
    fn bundled_upgrade_failure_should_rollback_and_write_machine_readable_audit() {
        let (_dir, sqlite_path) = temp_sqlite_path();
        init_sqlite(&sqlite_path).expect("first init sqlite");

        let conn = Connection::open(sqlite_path.clone()).expect("open sqlite");
        let mut baseline_stmt = conn
            .prepare("SELECT dimsum_id, version FROM dimsums ORDER BY dimsum_id ASC")
            .expect("prepare baseline query");
        let baseline_rows = baseline_stmt
            .query_map([], |r| Ok((r.get::<_, String>(0)?, r.get::<_, String>(1)?)))
            .expect("query baseline");
        let mut baseline = Vec::new();
        for row in baseline_rows {
            baseline.push(row.expect("read baseline row"));
        }
        drop(baseline_stmt);

        conn.execute(
            "INSERT INTO settings(key, value_json, updated_at) VALUES ('__test.failBundledUpgradeAfter', '1', 1) \
             ON CONFLICT(key) DO UPDATE SET value_json='1', updated_at=excluded.updated_at",
            [],
        )
        .expect("set failpoint");
        let err = init_sqlite(&sqlite_path).expect_err("upgrade must fail in test failpoint");
        conn.execute(
            "DELETE FROM settings WHERE key='__test.failBundledUpgradeAfter'",
            [],
        )
        .expect("clear failpoint");

        let err_text = err.to_string();
        assert!(
            err_text.contains("DIMSUM_UPGRADE_FAILED_ROLLBACK_APPLIED"),
            "unexpected error: {err_text}"
        );

        let mut after_stmt = conn
            .prepare("SELECT dimsum_id, version FROM dimsums ORDER BY dimsum_id ASC")
            .expect("prepare after query");
        let after_rows = after_stmt
            .query_map([], |r| Ok((r.get::<_, String>(0)?, r.get::<_, String>(1)?)))
            .expect("query after");
        let mut after = Vec::new();
        for row in after_rows {
            after.push(row.expect("read after row"));
        }
        assert_eq!(after, baseline, "upgrade failure must rollback dimsum versions");

        let (action, payload_json): (String, String) = conn
            .query_row(
                "SELECT action, payload_json FROM audit_events WHERE action='dimsum.upgrade.rollback' ORDER BY id DESC LIMIT 1",
                [],
                |r| Ok((r.get(0)?, r.get(1)?)),
            )
            .expect("rollback audit should exist");
        assert_eq!(action, "dimsum.upgrade.rollback");
        let payload: serde_json::Value = serde_json::from_str(&payload_json).expect("parse payload");
        assert_eq!(
            payload["code"],
            serde_json::json!("DIMSUM_UPGRADE_FAILED_ROLLBACK_APPLIED")
        );
        assert_eq!(payload["rolledBack"], serde_json::json!(true));
    }

    #[test]
    fn migration_retry_from_partial_state_should_be_idempotent_and_safe() {
        let (_dir, sqlite_path) = temp_sqlite_path();
        let conn = Connection::open(sqlite_path.clone()).expect("open sqlite");
        conn.execute_batch(
            "PRAGMA foreign_keys = ON;\
             CREATE TABLE IF NOT EXISTS sessions (\
               id INTEGER PRIMARY KEY AUTOINCREMENT,\
               session_id TEXT NOT NULL UNIQUE,\
               title TEXT,\
               created_at INTEGER NOT NULL,\
               updated_at INTEGER NOT NULL\
             );",
        )
        .expect("seed partial schema");

        init_sqlite(&sqlite_path).expect("retry from partial state should succeed");
        init_sqlite(&sqlite_path).expect("rerun migration should stay idempotent");

        let default_session_count: i64 = conn
            .query_row(
                "SELECT COUNT(1) FROM sessions WHERE session_id='default'",
                [],
                |r| r.get(0),
            )
            .expect("count default session");
        assert_eq!(default_session_count, 1);

        let allow_lan_setting_count: i64 = conn
            .query_row(
                "SELECT COUNT(1) FROM settings WHERE key='gateway.allowLan'",
                [],
                |r| r.get(0),
            )
            .expect("count default setting");
        assert_eq!(allow_lan_setting_count, 1);

        let dimsum_count: i64 = conn
            .query_row("SELECT COUNT(1) FROM dimsums", [], |r| r.get(0))
            .expect("count dimsums");
        assert!(dimsum_count > 0, "bundled dimsums should still be seeded");
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

    #[error("storage: {0}")]
    Storage(#[from] StorageError),

    #[error("unauthorized")]
    Unauthorized,

    #[error("handshake: {0}")]
    Handshake(String),

    #[error("protocol: {0}")]
    Protocol(String),
}
