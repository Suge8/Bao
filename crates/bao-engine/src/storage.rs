use std::sync::Arc;

use bao_storage::{Storage, StorageError, TaskRecord};

#[derive(Debug, Clone)]
pub struct TaskRunRecord {
    pub task_id: String,
    pub status: String,
    pub error: Option<String>,
}

pub trait StorageFacade: Send + Sync {
    fn fetch_due_tasks(&self, now_ts: i64, limit: i64) -> Result<Vec<TaskRecord>, StorageError>;
    fn mark_task_run(&self, record: &TaskRunRecord, now_ts: i64) -> Result<(), StorageError>;
}

#[derive(Clone)]
pub struct SqliteStorage {
    inner: Arc<Storage>,
}

impl SqliteStorage {
    pub fn new(inner: Arc<Storage>) -> Self {
        Self { inner }
    }
}

impl StorageFacade for SqliteStorage {
    fn fetch_due_tasks(&self, now_ts: i64, limit: i64) -> Result<Vec<TaskRecord>, StorageError> {
        self.inner.fetch_due_tasks(now_ts, limit)
    }

    fn mark_task_run(&self, record: &TaskRunRecord, now_ts: i64) -> Result<(), StorageError> {
        self.inner
            .mark_task_run(&record.task_id, &record.status, record.error.as_deref(), now_ts)
    }
}
