use bao_api::{RouterOutputV1, TaskSpecV1, ToolCallIrV1};
use std::sync::Arc;

pub mod scheduler;
pub mod storage;

// -----------------------------
// Pipeline hooks (phase0: stubs)
// -----------------------------

pub trait RouterHook {
    fn route(&self, user_input: &str) -> RouterOutputV1;
}

pub trait MemoryHook {
    fn inject(&self, input: &str) -> String;
}

pub trait CorrectorHook {
    fn validate_tool_args(&self, tool_call: &ToolCallIrV1) -> Result<(), String>;
}

pub trait Provider {
    fn run(&self, input: &str) -> Result<String, String>;
}

// -----------------------------
// Scheduler (phase0: stubs)
// -----------------------------

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum TaskRunStatus {
    Success,
    Failed,
}

pub trait Scheduler {
    fn tick(&mut self, now_ts: i64);
    fn upsert_task(&mut self, task: TaskSpecV1);
    fn disable_task(&mut self, task_id: &str);
}

pub struct Engine;

impl Engine {
    pub fn new() -> Self {
        Self
    }

    pub fn scheduler(
        storage: Arc<dyn storage::StorageFacade>,
        runner: Arc<dyn bao_plugin_host::ToolRunner + Send + Sync>,
    ) -> scheduler::SchedulerService {
        scheduler::SchedulerService::new(storage, runner)
    }
}
