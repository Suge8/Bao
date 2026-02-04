use serde::{Deserialize, Serialize};

// -----------------------------
// Core IR / Schemas (V1)
// -----------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ToolCallSourceV1 {
    pub provider: String,
    pub model: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ToolCallIrV1 {
    pub id: String,
    pub name: String,
    pub args: serde_json::Value,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub quote: Option<String>,
    pub source: ToolCallSourceV1,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RouterPolicyV1 {
    pub mustTrigger: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RouterOutputV1 {
    pub matched: bool,
    pub confidence: f64,
    pub reasonCodes: Vec<String>,
    pub needsMemory: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub memoryQuery: Option<String>,

    #[serde(skip_serializing_if = "Option::is_none")]
    pub toolName: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub toolArgs: Option<serde_json::Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub quote: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub policy: Option<RouterPolicyV1>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BaoEventV1 {
    pub eventId: i64,
    pub ts: i64,
    pub r#type: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub sessionId: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub messageId: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub deviceId: Option<String>,
    pub payload: serde_json::Value,
}

// -----------------------------
// Memory Native (V1)
// -----------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum MemoryEvidenceKindV1 {
    Message,
    Event,
    Artifact,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MemoryEvidenceV1 {
    pub kind: MemoryEvidenceKindV1,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub messageId: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub eventId: Option<i64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub artifactSha256: Option<String>,
    pub weight: f64,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub note: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MemoryHitV1 {
    pub id: String,
    pub namespace: String,
    pub kind: String,
    pub title: String,
    pub snippet: String,
    pub score: f64,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub tags: Vec<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub status: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub updatedAt: Option<i64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub evidenceCount: Option<i64>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum MemoryMutationOpV1 {
    UPSERT,
    SUPERSEDE,
    DELETE,
    LINK,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MemoryItemV1 {
    #[serde(skip_serializing_if = "Option::is_none")]
    pub id: Option<String>,
    pub namespace: String,
    pub kind: String,
    pub title: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub content: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub json: Option<serde_json::Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub score: Option<f64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub status: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub sourceHash: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MemorySupersedeV1 {
    pub oldId: String,
    pub newId: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MemoryDeleteV1 {
    pub id: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MemoryLinkV1 {
    pub memoryId: String,
    pub evidence: MemoryEvidenceV1,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MemoryDangerousV1 {
    #[serde(skip_serializing_if = "Option::is_none")]
    pub needsUserConfirmation: Option<bool>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub reasons: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MemoryMutationV1 {
    pub op: MemoryMutationOpV1,
    pub idempotencyKey: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub reason: Option<String>,

    #[serde(skip_serializing_if = "Option::is_none")]
    pub memory: Option<MemoryItemV1>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub supersede: Option<MemorySupersedeV1>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub delete: Option<MemoryDeleteV1>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub link: Option<MemoryLinkV1>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MemoryMutationPlanV1 {
    pub planId: String,
    pub mutations: Vec<MemoryMutationV1>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub dangerous: Option<MemoryDangerousV1>,
}

// -----------------------------
// Scheduler (V1)
// -----------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum TaskScheduleKindV1 {
    Once,
    Interval,
    Cron,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TaskScheduleV1 {
    pub kind: TaskScheduleKindV1,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub runAtTs: Option<i64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub intervalMs: Option<i64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub cron: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub timezone: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TaskToolCallV1 {
    pub dimsumId: String,
    pub toolName: String,
    pub args: serde_json::Value,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum TaskActionKindV1 {
    ToolCall,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TaskActionV1 {
    pub kind: TaskActionKindV1,
    pub toolCall: TaskToolCallV1,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TaskPolicyV1 {
    #[serde(skip_serializing_if = "Option::is_none")]
    pub maxRetries: Option<i64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub timeoutMs: Option<i64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub killSwitchGroup: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TaskSpecV1 {
    pub id: String,
    pub title: String,
    pub enabled: bool,
    pub schedule: TaskScheduleV1,
    pub action: TaskActionV1,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub policy: Option<TaskPolicyV1>,
}

// -----------------------------
// Schema validation helpers (phase0: stub)
// -----------------------------

#[derive(Debug)]
pub struct SchemaValidationError {
    pub message: String,
}

pub fn validate_json_schema(
    _schema: &serde_json::Value,
    _instance: &serde_json::Value,
) -> Result<(), SchemaValidationError> {
    Ok(())
}
