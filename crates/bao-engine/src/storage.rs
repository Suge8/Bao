use std::sync::Arc;

use bao_storage::{
    MemoryItemRecord, MemoryLinkRecord, MemoryVersionRecord, Storage, StorageError, TaskRecord,
};
use serde_json::Value;

#[derive(Debug, Clone)]
pub struct TaskRunRecord {
    pub task_id: String,
    pub status: String,
    pub error: Option<String>,
}

pub trait StorageFacade: Send + Sync {
    fn fetch_due_tasks(&self, now_ts: i64, limit: i64) -> Result<Vec<TaskRecord>, StorageError>;
    fn mark_task_run(&self, record: &TaskRunRecord, now_ts: i64) -> Result<(), StorageError>;
    fn insert_event(
        &self,
        ts: i64,
        ty: &str,
        session_id: Option<&str>,
        message_id: Option<&str>,
        device_id: Option<&str>,
        payload: &Value,
    ) -> Result<i64, StorageError>;
    fn insert_audit_event(
        &self,
        ts: i64,
        action: &str,
        subject_type: &str,
        subject_id: &str,
        payload: &Value,
    ) -> Result<(), StorageError>;
    fn get_task_by_id(&self, task_id: &str) -> Result<Option<TaskRecord>, StorageError>;
    fn upsert_memory_item(&self, item: &MemoryItemRecord) -> Result<(), StorageError>;
    fn delete_memory_item(&self, memory_id: &str) -> Result<(), StorageError>;
    fn get_memory_item(&self, memory_id: &str) -> Result<Option<MemoryItemRecord>, StorageError>;
    fn insert_memory_version(&self, version: &MemoryVersionRecord) -> Result<(), StorageError>;
    fn insert_memory_link(&self, link: &MemoryLinkRecord) -> Result<(), StorageError>;
    fn list_memory_versions(
        &self,
        memory_id: &str,
    ) -> Result<Vec<MemoryVersionRecord>, StorageError>;
    fn get_memory_version(
        &self,
        version_id: &str,
    ) -> Result<Option<MemoryVersionRecord>, StorageError>;
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
        self.inner.mark_task_run(
            &record.task_id,
            &record.status,
            record.error.as_deref(),
            now_ts,
        )
    }

    fn insert_event(
        &self,
        ts: i64,
        ty: &str,
        session_id: Option<&str>,
        message_id: Option<&str>,
        device_id: Option<&str>,
        payload: &Value,
    ) -> Result<i64, StorageError> {
        self.inner
            .insert_event(ts, ty, session_id, message_id, device_id, payload)
    }

    fn insert_audit_event(
        &self,
        ts: i64,
        action: &str,
        subject_type: &str,
        subject_id: &str,
        payload: &Value,
    ) -> Result<(), StorageError> {
        self.inner
            .insert_audit_event(ts, action, subject_type, subject_id, payload)
    }

    fn get_task_by_id(&self, task_id: &str) -> Result<Option<TaskRecord>, StorageError> {
        self.inner.get_task_by_id(task_id)
    }

    fn upsert_memory_item(&self, item: &MemoryItemRecord) -> Result<(), StorageError> {
        self.inner.upsert_memory_item(item)
    }

    fn delete_memory_item(&self, memory_id: &str) -> Result<(), StorageError> {
        self.inner.delete_memory_item(memory_id)
    }

    fn get_memory_item(&self, memory_id: &str) -> Result<Option<MemoryItemRecord>, StorageError> {
        self.inner.get_memory_item(memory_id)
    }

    fn insert_memory_version(&self, version: &MemoryVersionRecord) -> Result<(), StorageError> {
        self.inner.insert_memory_version(version)
    }

    fn insert_memory_link(&self, link: &MemoryLinkRecord) -> Result<(), StorageError> {
        self.inner.insert_memory_link(link)
    }

    fn list_memory_versions(
        &self,
        memory_id: &str,
    ) -> Result<Vec<MemoryVersionRecord>, StorageError> {
        self.inner.list_memory_versions(memory_id)
    }

    fn get_memory_version(
        &self,
        version_id: &str,
    ) -> Result<Option<MemoryVersionRecord>, StorageError> {
        self.inner.get_memory_version(version_id)
    }
}
