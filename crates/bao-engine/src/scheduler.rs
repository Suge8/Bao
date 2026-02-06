use std::sync::{Arc, Mutex};

use bao_api::TaskSpecV1;
use bao_plugin_host::{PluginHostError, ToolRunResult, ToolRunner};
use bao_storage::TaskRecord;

use crate::storage::{StorageFacade, TaskRunRecord};
use serde_json::{json, Value};

pub struct SchedulerService {
    storage: Arc<dyn StorageFacade>,
    runner: Arc<dyn ToolRunner + Send + Sync>,
    running_groups: Arc<Mutex<Vec<String>>>,
}

impl SchedulerService {
    pub fn new(storage: Arc<dyn StorageFacade>, runner: Arc<dyn ToolRunner + Send + Sync>) -> Self {
        Self {
            storage,
            runner,
            running_groups: Arc::new(Mutex::new(Vec::new())),
        }
    }

    pub fn tick(&self, now_ts: i64) {
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
            let out = g.clone();
            g.clear();
            out
        };
        for group in groups {
            self.runner.kill_group(&group);
        }
    }

    pub fn run_task_now(&self, task_id: &str, now_ts: i64) {
        let task = match self.storage.get_task_by_id(task_id) {
            Ok(Some(t)) => t,
            _ => return,
        };

        self.execute_task(task, now_ts);
    }

    fn execute_task(&self, task: TaskRecord, now_ts: i64) {
        let group = task
            .kill_switch_group
            .clone()
            .unwrap_or_else(|| task.id.clone());
        {
            let mut g = self
                .running_groups
                .lock()
                .expect("running_groups mutex poisoned");
            g.push(group.clone());
        }

        let task_id = task.id.clone();
        let _ = self.storage.insert_event(
            now_ts,
            "task.run.started",
            None,
            None,
            None,
            &json!({"taskId": task_id, "group": group}),
        );
        let _ = self.storage.insert_audit_event(
            now_ts,
            "task.run.started",
            "task",
            &task_id,
            &json!({"group": group.clone()}),
        );

        let run = self
            .runner
            .run_tool(&task.tool_dimsum_id, &task.tool_name, &task.tool_args);
        let (record, run_meta) = resolve_run_result(task_id.clone(), run);

        let _ = self.storage.mark_task_run(&record, now_ts);
        let _ = self.storage.insert_event(
            now_ts,
            "task.run.finished",
            None,
            None,
            None,
            &json!({
                "taskId": task_id,
                "group": group,
                "status": record.status.clone(),
                "error": record.error.clone(),
                "result": run_meta,
            }),
        );
        let _ = self.storage.insert_audit_event(
            now_ts,
            "task.run.finished",
            "task",
            &task_id,
            &json!({"status": record.status, "error": record.error, "result": run_meta}),
        );

        let mut g = self
            .running_groups
            .lock()
            .expect("running_groups mutex poisoned");
        g.retain(|x| x != &group);
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

pub struct TaskUpsert {
    pub spec: TaskSpecV1,
}
