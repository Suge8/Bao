use std::{
    path::{Path, PathBuf},
    sync::{Arc, Mutex},
    time::Duration,
};

use bao_api::{BaoEventV1, MemoryMutationPlanV1, TaskSpecV1};
use bao_gateway::{GatewayConfig, GatewayHandle, GatewayServer};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use thiserror::Error;
use tauri::{Emitter, Manager};
use tokio::{
    sync::{broadcast, oneshot},
    time,
};
use ::time::OffsetDateTime;

// -----------------------------
// Errors
// -----------------------------

#[derive(Debug, Error)]
enum DesktopError {
    #[error("tauri: missing app data dir")]
    MissingAppDataDir,

    #[error("io: {0}")]
    Io(#[from] std::io::Error),

    #[error("gateway: {0}")]
    Gateway(#[from] bao_gateway::GatewayError),

    #[error("internal: {0}")]
    Internal(String),
}

type DesktopResult<T> = Result<T, DesktopError>;

// -----------------------------
// IPC types
// -----------------------------

#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
struct UpdateSettingInput {
    key: String,
    value: Value,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
struct AllowLanInput {
    allow: bool,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct PairingTokenOutput {
    token: String,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
struct CreateTaskInput {
    spec: TaskSpecV1,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
struct UpdateTaskInput {
    spec: TaskSpecV1,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
struct SearchIndexInput {
    query: String,
    #[serde(default = "default_search_limit")]
    limit: i64,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
struct TaskIdInput {
    task_id: String,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
struct MemoryGetItemsInput {
    ids: Vec<String>,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
struct MemoryGetTimelineInput {
    namespace: Option<String>,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
struct MemoryApplyPlanInput {
    plan: MemoryMutationPlanV1,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
struct MemoryRollbackInput {
    memory_id: String,
    version_id: String,
}

fn default_search_limit() -> i64 {
    50
}

// -----------------------------
// App state
// -----------------------------

struct AppState {
    engine: bao_engine::Engine,
    storage: Arc<bao_storage::Storage>,
    plugin_runner: Arc<bao_plugin_host::mock_runner::MockToolRunner>,
    scheduler: Arc<bao_engine::scheduler::SchedulerService>,

    gateway: GatewayServer,
    gateway_handle: GatewayHandle,

    // start/stop management for background tasks
    gateway_task: Mutex<Option<tokio::task::JoinHandle<()>>>,
    stop_tx: Mutex<Option<oneshot::Sender<()>>>,

    // local event tailer -> (tauri emit + optional other subscribers)
    event_tx: broadcast::Sender<BaoEventV1>,

    // phase1 minimal scheduler tick task (abort-only)
    scheduler_task: Mutex<Option<tauri::async_runtime::JoinHandle<()>>>,
}

impl AppState {
    fn open(app_data_dir: PathBuf) -> DesktopResult<Self> {
        let sqlite_path = ensure_sqlite_path(&app_data_dir, "bao.sqlite")?;
        let (gateway, gateway_handle) = GatewayServer::open(&sqlite_path)?;

        let (event_tx, _) = broadcast::channel(256);

        Ok(Self {
            engine: bao_engine::Engine::new(),
            storage: Arc::new(
                bao_storage::Storage::open(sqlite_path.clone())
                    .map_err(|e| DesktopError::Internal(e.to_string()))?,
            ),
            plugin_runner: Arc::new(bao_plugin_host::mock_runner::MockToolRunner::new()),
            scheduler: Arc::new(bao_engine::Engine::scheduler(
                Arc::new(bao_engine::storage::SqliteStorage::new(Arc::new(
                    bao_storage::Storage::open(sqlite_path.clone())
                        .map_err(|e| DesktopError::Internal(e.to_string()))?,
                ))),
                Arc::new(bao_plugin_host::mock_runner::MockToolRunner::new()),
            )),

            gateway,
            gateway_handle,

            gateway_task: Mutex::new(None),
            stop_tx: Mutex::new(None),
            event_tx,

            scheduler_task: Mutex::new(None),
        })
    }
}

fn ensure_sqlite_path(app_data_dir: &Path, file_name: &str) -> DesktopResult<String> {
    std::fs::create_dir_all(app_data_dir)?;
    Ok(app_data_dir.join(file_name).to_string_lossy().to_string())
}

// -----------------------------
// Commands (Tauri IPC)
// -----------------------------

#[tauri::command(rename = "sendMessage")]
async fn send_message(
    state: tauri::State<'_, Arc<AppState>>,
    sessionId: String,
    text: String,
) -> Result<BaoEventV1, String> {
    state
        .gateway_handle
        .send_message(sessionId, text)
        .await
        .map_err(|e| e.to_string())
}

#[tauri::command(rename = "listSessions")]
async fn list_sessions(state: tauri::State<'_, Arc<AppState>>) -> Result<BaoEventV1, String> {
    state
        .gateway_handle
        .list_sessions()
        .await
        .map_err(|e| e.to_string())
}

#[tauri::command(rename = "listTasks")]
async fn list_tasks(state: tauri::State<'_, Arc<AppState>>) -> Result<BaoEventV1, String> {
    state.gateway_handle.list_tasks().await.map_err(|e| e.to_string())
}

#[tauri::command(rename = "createTask")]
async fn create_task(
    state: tauri::State<'_, Arc<AppState>>,
    input: CreateTaskInput,
) -> Result<BaoEventV1, String> {
    state
        .gateway_handle
        .create_task(input.spec)
        .await
        .map_err(|e| e.to_string())
}

#[tauri::command(rename = "updateTask")]
async fn update_task(
    state: tauri::State<'_, Arc<AppState>>,
    input: UpdateTaskInput,
) -> Result<BaoEventV1, String> {
    state
        .gateway_handle
        .update_task(input.spec)
        .await
        .map_err(|e| e.to_string())
}

#[tauri::command(rename = "enableTask")]
async fn enable_task(
    state: tauri::State<'_, Arc<AppState>>,
    input: TaskIdInput,
) -> Result<BaoEventV1, String> {
    state
        .gateway_handle
        .enable_task(input.task_id)
        .await
        .map_err(|e| e.to_string())
}

#[tauri::command(rename = "disableTask")]
async fn disable_task(
    state: tauri::State<'_, Arc<AppState>>,
    input: TaskIdInput,
) -> Result<BaoEventV1, String> {
    state
        .gateway_handle
        .disable_task(input.task_id)
        .await
        .map_err(|e| e.to_string())
}

#[tauri::command(rename = "runTaskNow")]
async fn run_task_now(
    state: tauri::State<'_, Arc<AppState>>,
    input: TaskIdInput,
) -> Result<BaoEventV1, String> {
    state
        .gateway_handle
        .run_task_now(input.task_id)
        .await
        .map_err(|e| e.to_string())
}

#[tauri::command(rename = "listDimsums")]
async fn list_dimsums(state: tauri::State<'_, Arc<AppState>>) -> Result<BaoEventV1, String> {
    state.gateway_handle.list_dimsums().await.map_err(|e| e.to_string())
}

#[tauri::command(rename = "listMemories")]
async fn list_memories(state: tauri::State<'_, Arc<AppState>>) -> Result<BaoEventV1, String> {
    state.gateway_handle.list_memories().await.map_err(|e| e.to_string())
}

#[tauri::command(rename = "searchIndex")]
async fn search_index(
    state: tauri::State<'_, Arc<AppState>>,
    input: SearchIndexInput,
) -> Result<BaoEventV1, String> {
    state
        .gateway_handle
        .search_index(input.query, input.limit)
        .await
        .map_err(|e| e.to_string())
}

#[tauri::command(rename = "getItems")]
async fn memory_get_items(
    state: tauri::State<'_, Arc<AppState>>,
    input: MemoryGetItemsInput,
) -> Result<BaoEventV1, String> {
    state
        .gateway_handle
        .get_items(input.ids)
        .await
        .map_err(|e| e.to_string())
}

#[tauri::command(rename = "getTimeline")]
async fn memory_get_timeline(
    state: tauri::State<'_, Arc<AppState>>,
    input: MemoryGetTimelineInput,
) -> Result<BaoEventV1, String> {
    state
        .gateway_handle
        .get_timeline(input.namespace)
        .await
        .map_err(|e| e.to_string())
}

#[tauri::command(rename = "applyMutationPlan")]
async fn memory_apply_mutation_plan(
    state: tauri::State<'_, Arc<AppState>>,
    input: MemoryApplyPlanInput,
) -> Result<BaoEventV1, String> {
    state
        .gateway_handle
        .apply_mutation_plan(input.plan)
        .await
        .map_err(|e| e.to_string())
}

#[tauri::command(rename = "rollbackVersion")]
async fn memory_rollback_version(
    state: tauri::State<'_, Arc<AppState>>,
    input: MemoryRollbackInput,
) -> Result<BaoEventV1, String> {
    state
        .gateway_handle
        .rollback_version(input.memory_id, input.version_id)
        .await
        .map_err(|e| e.to_string())
}

#[tauri::command(rename = "getSettings")]
async fn get_settings(state: tauri::State<'_, Arc<AppState>>) -> Result<BaoEventV1, String> {
    state.gateway_handle.get_settings().await.map_err(|e| e.to_string())
}

#[tauri::command(rename = "updateSettings")]
async fn update_settings(
    state: tauri::State<'_, Arc<AppState>>,
    input: UpdateSettingInput,
) -> Result<BaoEventV1, String> {
    state
        .gateway_handle
        .update_setting(input.key, input.value)
        .await
        .map_err(|e| e.to_string())
}

#[tauri::command(rename = "generatePairingToken")]
async fn gateway_generate_pairing_token(
    state: tauri::State<'_, Arc<AppState>>,
) -> Result<PairingTokenOutput, String> {
    Ok(PairingTokenOutput {
        token: state.gateway_handle.create_pairing_token(),
    })
}

#[tauri::command(rename = "gatewayStart")]
async fn gateway_start(state: tauri::State<'_, Arc<AppState>>) -> Result<(), String> {
    // Idempotent: if already started, do nothing.
    if state.gateway_task.lock().expect("gateway_task mutex poisoned").is_some() {
        return Ok(());
    }

    let (stop_tx, mut stop_rx) = oneshot::channel::<()>();
    *state.stop_tx.lock().expect("stop_tx mutex poisoned") = Some(stop_tx);

    let gateway = state.gateway.clone();
    let jh = tokio::spawn(async move {
        let fut = gateway.start(GatewayConfig::default());
        tokio::select! {
            _ = &mut stop_rx => {
                // phase1: gateway server has no graceful shutdown.
                // We rely on aborting this task.
            }
            _ = fut => {
                // GatewayServer::start runs forever; ignore result.
            }
        }
    });

    *state.gateway_task.lock().expect("gateway_task mutex poisoned") = Some(jh);
    Ok(())
}

#[tauri::command(rename = "gatewaySetAllowLan")]
async fn gateway_set_allow_lan(
    state: tauri::State<'_, Arc<AppState>>,
    input: AllowLanInput,
) -> Result<(), String> {
    state.gateway_handle.set_allow_lan(input.allow);
    // Persist as a setting as well (best-effort).
    let _ = state
        .gateway_handle
        .update_setting(
            "gateway.allowLan".to_string(),
            serde_json::json!(input.allow),
        )
        .await;
    Ok(())
}

#[tauri::command(rename = "gatewayStop")]
async fn gateway_stop(state: tauri::State<'_, Arc<AppState>>) -> Result<(), String> {
    if let Some(tx) = state.stop_tx.lock().expect("stop_tx mutex poisoned").take() {
        let _ = tx.send(());
    }
    if let Some(jh) = state.gateway_task.lock().expect("gateway_task mutex poisoned").take() {
        jh.abort();
    }
    Ok(())
}

#[tauri::command(rename = "killSwitchStopAll")]
async fn kill_switch_stop_all(state: tauri::State<'_, Arc<AppState>>) -> Result<(), String> {
    state.scheduler.kill_switch_stop_all();
    if let Some(jh) = state
        .scheduler_task
        .lock()
        .expect("scheduler_task mutex poisoned")
        .take()
    {
        jh.abort();
    }

    // Reuse gateway_stop semantics.
    gateway_stop(state).await
}

// -----------------------------
// Event bridge (SQLite events -> tauri event)
// -----------------------------

async fn spawn_event_tailer(app: tauri::AppHandle, state: Arc<AppState>) {
    let mut cursor: Option<i64> = None;
    let mut ticker = time::interval(Duration::from_millis(250));

    loop {
        ticker.tick().await;

        let events = match state.gateway_handle.events_since(cursor, 5000).await {
            Ok(v) => v,
            Err(_) => continue,
        };

        for evt in events {
            cursor = Some(cursor.unwrap_or(0).max(evt.eventId));
            let _ = state.event_tx.send(evt.clone());
            let _ = app.emit("bao:event", evt);
        }
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .setup(|app| {
            let app_data_dir = app
                .path()
                .app_data_dir()
                .map_err(|_| DesktopError::MissingAppDataDir)?;

            let state = Arc::new(AppState::open(app_data_dir)?);

            // Spawn local tailer that bridges to frontend.
            let handle = app.handle().clone();
            let st = state.clone();
            tauri::async_runtime::spawn(async move { spawn_event_tailer(handle, st).await });

            // Phase1 scheduler tick: we don't have bao-engine/bao-plugin-host implementations yet.
            // We start a real scheduler tick that fetches due tasks and executes tools.
            let st = state.clone();
            let mut sched_guard = st
                .scheduler_task
                .lock()
                .expect("scheduler_task mutex poisoned");
            if sched_guard.is_none() {
                let st2 = st.clone();
                let jh = tauri::async_runtime::spawn(async move {
                    let mut ticker = time::interval(Duration::from_secs(1));
                    loop {
                        ticker.tick().await;
                        let now_ts = OffsetDateTime::now_utc().unix_timestamp();
                        st2.scheduler.tick(now_ts);
                    }
                });
                *sched_guard = Some(jh);
            }

            app.manage(state);
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            send_message,
            list_sessions,
            list_tasks,
            create_task,
            update_task,
            enable_task,
            disable_task,
            run_task_now,
            list_dimsums,
            list_memories,
            search_index,
            memory_get_items,
            memory_get_timeline,
            memory_apply_mutation_plan,
            memory_rollback_version,
            get_settings,
            update_settings,
            gateway_start,
            gateway_stop,
            gateway_generate_pairing_token,
            gateway_set_allow_lan,
            kill_switch_stop_all,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
