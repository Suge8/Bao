use std::sync::{Arc, Mutex};

use bao_api::TaskSpecV1;
use bao_plugin_host::ToolRunner;

use crate::storage::{StorageFacade, TaskRunRecord};

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
            let group = task.kill_switch_group.clone().unwrap_or_else(|| task.id.clone());
            {
                let mut g = self.running_groups.lock().expect("running_groups mutex poisoned");
                g.push(group.clone());
            }

            let run = self.runner.run_tool(&task.tool_dimsum_id, &task.tool_name, &task.tool_args);
            let record = match run {
                Ok(result) if result.ok => TaskRunRecord {
                    task_id: task.id.clone(),
                    status: "success".to_string(),
                    error: None,
                },
                Ok(result) => TaskRunRecord {
                    task_id: task.id.clone(),
                    status: "failed".to_string(),
                    error: Some(format!("tool failed: {}", result.output)),
                },
                Err(err) => TaskRunRecord {
                    task_id: task.id.clone(),
                    status: "failed".to_string(),
                    error: Some(err.message),
                },
            };

            let _ = self.storage.mark_task_run(&record, now_ts);

            let mut g = self.running_groups.lock().expect("running_groups mutex poisoned");
            g.retain(|x| x != &group);
        }
    }

    pub fn kill_switch_stop_all(&self) {
        let groups = {
            let mut g = self.running_groups.lock().expect("running_groups mutex poisoned");
            let out = g.clone();
            g.clear();
            out
        };
        for group in groups {
            self.runner.kill_group(&group);
        }
    }
}

pub struct TaskUpsert {
    pub spec: TaskSpecV1,
}

