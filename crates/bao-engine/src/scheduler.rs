use std::collections::{HashMap, HashSet};
use std::sync::{Arc, Mutex};

use bao_api::TaskSpecV1;
use bao_plugin_host::{PluginHostError, ToolRunResult, ToolRunner};
use bao_storage::TaskRecord;

use crate::storage::{StorageFacade, TaskRunRecord};
use serde_json::{json, Value};

pub struct SchedulerService {
    storage: Arc<dyn StorageFacade>,
    runner: Arc<dyn ToolRunner + Send + Sync>,
    running_groups: Arc<Mutex<HashMap<String, RunningTask>>>,
    crash_injector: Arc<dyn CrashInjector>,
}

const CAP_SETTINGS_KEY: &str = "permissions.capabilities";
const CODE_PERMISSION_CAPABILITY_DENIED: &str = "PERMISSION_CAPABILITY_DENIED";
const CODE_PERMISSION_CAPABILITY_REVOKED: &str = "PERMISSION_CAPABILITY_REVOKED";
const DEFAULT_TASK_SESSION_ID: &str = "default";
const DEFAULT_TASK_SESSION_TITLE: &str = "Default Session";

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum CrashPoint {
    AfterTaskStartedEvent,
}

pub trait CrashInjector: Send + Sync {
    fn should_crash(&self, point: CrashPoint, task_id: &str) -> bool;
}

#[derive(Debug)]
struct NoCrashInjector;

impl CrashInjector for NoCrashInjector {
    fn should_crash(&self, _point: CrashPoint, _task_id: &str) -> bool {
        false
    }
}

#[derive(Clone)]
struct RunningTask {
    task_id: String,
    required_caps: Vec<String>,
}

impl SchedulerService {
    pub fn new(storage: Arc<dyn StorageFacade>, runner: Arc<dyn ToolRunner + Send + Sync>) -> Self {
        Self {
            storage,
            runner,
            running_groups: Arc::new(Mutex::new(HashMap::new())),
            crash_injector: Arc::new(NoCrashInjector),
        }
    }

    pub fn with_crash_injector(mut self, crash_injector: Arc<dyn CrashInjector>) -> Self {
        self.crash_injector = crash_injector;
        self
    }

    pub fn tick(&self, now_ts: i64) {
        self.enforce_capability_gate(now_ts);
        let due = match self.storage.fetch_due_tasks(now_ts, 64) {
            Ok(v) => v,
            Err(_) => return,
        };
        for task in due {
            self.execute_task(task, now_ts);
        }
    }

    pub fn kill_switch_stop_all(&self) {
        let groups = {
            let mut g = self
                .running_groups
                .lock()
                .expect("running_groups mutex poisoned");
            let out = g.keys().cloned().collect::<Vec<_>>();
            g.clear();
            out
        };
        for group in groups {
            self.runner.kill_group(&group);
        }
    }

    pub fn run_task_now(&self, task_id: &str, now_ts: i64) {
        self.enforce_capability_gate(now_ts);
        let task = match self.storage.get_task_by_id(task_id) {
            Ok(Some(t)) => t,
            _ => return,
        };

        self.execute_task(task, now_ts);
    }

    pub fn enforce_capability_gate(&self, now_ts: i64) {
        let policy = self.load_capability_policy();
        let running = {
            let g = self
                .running_groups
                .lock()
                .expect("running_groups mutex poisoned");
            g.clone()
        };

        let mut revoked = Vec::new();
        for (group, meta) in running {
            let denied = denied_capabilities(&policy, &meta.required_caps);
            if denied.is_empty() {
                continue;
            }
            revoked.push((group, meta, denied));
        }

        if revoked.is_empty() {
            return;
        }

        {
            let mut g = self
                .running_groups
                .lock()
                .expect("running_groups mutex poisoned");
            for (group, _, _) in &revoked {
                g.remove(group);
            }
        }

        for (group, meta, denied) in revoked {
            self.runner.kill_group(&group);
            let payload = json!({
                "taskId": meta.task_id,
                "group": group,
                "requiredCapabilities": meta.required_caps,
                "deniedCapabilities": denied,
                "code": CODE_PERMISSION_CAPABILITY_REVOKED,
            });
            self.emit_task_action(
                now_ts,
                "task.run.revoked",
                &meta.task_id,
                &payload,
                &payload,
            );
            self.send_task_chat_reminder(
                now_ts,
                &meta.task_id,
                "任务执行被中止（权限已撤销）",
                Some(denied.join(",")),
            );
        }
    }

    fn execute_task(&self, task: TaskRecord, now_ts: i64) {
        let required_caps = self
            .storage
            .get_tool_permissions(&task.tool_dimsum_id, &task.tool_name)
            .unwrap_or_default();
        let policy = self.load_capability_policy();
        let denied_caps = denied_capabilities(&policy, &required_caps);

        let group = task
            .kill_switch_group
            .clone()
            .unwrap_or_else(|| task.id.clone());

        let task_id = task.id.clone();
        if !denied_caps.is_empty() {
            let error = format!(
                "{}: {}",
                CODE_PERMISSION_CAPABILITY_DENIED,
                denied_caps.join(",")
            );
            let payload = json!({
                "taskId": task_id,
                "group": group,
                "requiredCapabilities": required_caps,
                "deniedCapabilities": denied_caps,
                "code": CODE_PERMISSION_CAPABILITY_DENIED,
            });
            let _ = self.storage.mark_task_run(
                &TaskRunRecord {
                    task_id: task.id.clone(),
                    status: "failed".to_string(),
                    error: Some(error),
                },
                now_ts,
            );
            self.emit_task_action(now_ts, "task.run.rejected", &task.id, &payload, &payload);
            self.send_task_chat_reminder(
                now_ts,
                &task.title,
                "任务执行被拒绝（权限不足）",
                Some(denied_caps.join(",")),
            );
            return;
        }

        {
            let mut g = self
                .running_groups
                .lock()
                .expect("running_groups mutex poisoned");
            g.insert(
                group.clone(),
                RunningTask {
                    task_id: task.id.clone(),
                    required_caps: required_caps.clone(),
                },
            );
        }

        let started_event_payload = json!({"taskId": task_id.clone(), "group": group.clone()});
        let started_audit_payload = json!({"group": group.clone()});
        self.emit_task_action(
            now_ts,
            "task.run.started",
            &task_id,
            &started_event_payload,
            &started_audit_payload,
        );
        if self
            .crash_injector
            .should_crash(CrashPoint::AfterTaskStartedEvent, &task_id)
        {
            panic!("crash injected at AfterTaskStartedEvent for task {task_id}");
        }

        let run = self
            .runner
            .run_tool(&task.tool_dimsum_id, &task.tool_name, &task.tool_args);
        let (record, run_meta) = resolve_run_result(task_id.clone(), run);

        let _ = self.storage.mark_task_run(&record, now_ts);
        let finished_event_payload = json!({
            "taskId": task_id.clone(),
            "group": group.clone(),
            "status": record.status.clone(),
            "error": record.error.clone(),
            "result": run_meta,
        });
        let finished_audit_payload = json!({
            "status": record.status,
            "error": record.error,
            "result": run_meta
        });
        self.emit_task_action(
            now_ts,
            "task.run.finished",
            &task_id,
            &finished_event_payload,
            &finished_audit_payload,
        );
        if record.status == "success" {
            self.send_task_chat_reminder(now_ts, &task.title, "任务已完成", None);
        } else {
            self.send_task_chat_reminder(now_ts, &task.title, "任务执行失败", record.error.clone());
        }

        let mut g = self
            .running_groups
            .lock()
            .expect("running_groups mutex poisoned");
        g.remove(&group);
    }

    fn load_capability_policy(&self) -> CapabilityPolicy {
        match self.storage.get_setting_json(CAP_SETTINGS_KEY) {
            Ok(Some(value)) => CapabilityPolicy::AllowSet(parse_allowed_caps(value)),
            Ok(None) | Err(_) => CapabilityPolicy::AllowAll,
        }
    }

    fn send_task_chat_reminder(
        &self,
        now_ts: i64,
        task_title: &str,
        summary: &str,
        detail: Option<String>,
    ) {
        if self
            .storage
            .ensure_session_exists(
                DEFAULT_TASK_SESSION_ID,
                Some(DEFAULT_TASK_SESSION_TITLE),
                now_ts,
            )
            .is_err()
        {
            return;
        }

        let content = format_task_reminder_content(task_title, summary, detail.as_deref());

        let message_id = match self.storage.append_message(
            DEFAULT_TASK_SESSION_ID,
            "assistant",
            &content,
            now_ts,
        ) {
            Ok(id) => id,
            Err(_) => return,
        };

        let payload = json!({
            "sessionId": DEFAULT_TASK_SESSION_ID,
            "messageId": message_id,
            "role": "assistant",
            "content": content,
        });
        let _ = self.storage.insert_event(
            now_ts,
            "message.send",
            Some(DEFAULT_TASK_SESSION_ID),
            Some(message_id.as_str()),
            None,
            &payload,
        );
    }

    fn emit_task_action(
        &self,
        now_ts: i64,
        action: &str,
        task_id: &str,
        event_payload: &Value,
        audit_payload: &Value,
    ) {
        let _ = self
            .storage
            .insert_event(now_ts, action, None, None, None, event_payload);
        let _ = self
            .storage
            .insert_audit_event(now_ts, action, "task", task_id, audit_payload);
    }
}

#[derive(Debug, Clone)]
enum CapabilityPolicy {
    AllowAll,
    AllowSet(HashSet<String>),
}

fn parse_allowed_caps(value: Value) -> HashSet<String> {
    if let Some(items) = value.as_array() {
        return items
            .iter()
            .filter_map(|item| item.as_str().map(str::to_string))
            .collect();
    }

    if let Some(map) = value.as_object() {
        if let Some(caps) = map.get("caps").and_then(|v| v.as_array()) {
            return caps
                .iter()
                .filter_map(|item| item.as_str().map(str::to_string))
                .collect();
        }
        return map
            .iter()
            .filter_map(|(key, val)| {
                val.as_bool()
                    .filter(|allowed| *allowed)
                    .map(|_| key.clone())
            })
            .collect();
    }

    HashSet::new()
}

fn denied_capabilities(policy: &CapabilityPolicy, required_caps: &[String]) -> Vec<String> {
    match policy {
        CapabilityPolicy::AllowAll => Vec::new(),
        CapabilityPolicy::AllowSet(allow_set) => required_caps
            .iter()
            .filter(|cap| !allow_set.contains(cap.as_str()))
            .cloned()
            .collect(),
    }
}

fn resolve_run_result(
    task_id: String,
    run: Result<ToolRunResult, PluginHostError>,
) -> (TaskRunRecord, Value) {
    match run {
        Ok(result) if result.ok => (
            TaskRunRecord {
                task_id,
                status: "success".to_string(),
                error: None,
            },
            json!({"ok": true, "output": result.output}),
        ),
        Ok(result) => (
            TaskRunRecord {
                task_id,
                status: "failed".to_string(),
                error: Some(format!("tool failed: {}", result.output)),
            },
            json!({"ok": false, "output": result.output}),
        ),
        Err(err) => {
            let error_message = err.message;
            let error_code = err.code;
            (
                TaskRunRecord {
                    task_id,
                    status: "failed".to_string(),
                    error: Some(error_message.clone()),
                },
                json!({"ok": false, "error": {"code": error_code, "message": error_message}}),
            )
        }
    }
}

fn format_task_reminder_content(task_title: &str, summary: &str, detail: Option<&str>) -> String {
    match detail {
        Some(err) if !err.trim().is_empty() => {
            format!("[任务提醒] {summary}：{task_title}。\n详情：{err}")
        }
        _ => format!("[任务提醒] {summary}：{task_title}"),
    }
}

pub struct TaskUpsert {
    pub spec: TaskSpecV1,
}
