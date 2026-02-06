use std::sync::Arc;

use bao_api::{RouterOutputV1, RouterPolicyV1, TaskSpecV1, ToolCallIrV1};
use serde_json::Value;

pub mod scheduler;
pub mod storage;

pub trait RouterHook {
    fn route(&self, user_input: &str) -> RouterOutputV1;
}

pub trait MemoryHook {
    fn inject(&self, input: &str) -> String;
}

pub trait CorrectorHook {
    fn validate_tool_args(&self, tool_call: &ToolCallIrV1) -> Result<(), String>;
}

#[derive(Debug, Clone, Copy, Default)]
pub struct DefaultRouterHook;

impl RouterHook for DefaultRouterHook {
    fn route(&self, user_input: &str) -> RouterOutputV1 {
        let input = user_input.trim();
        if input.is_empty() {
            return RouterOutputV1 {
                matched: false,
                confidence: 0.0,
                reasonCodes: vec!["empty_input".to_string()],
                needsMemory: false,
                memoryQuery: None,
                toolName: None,
                toolArgs: None,
                quote: None,
                policy: None,
            };
        }

        if input.starts_with("/tool ") {
            let rest = input.trim_start_matches("/tool").trim();
            let mut parts = rest.splitn(2, ' ');
            let tool_name = parts
                .next()
                .map(str::trim)
                .filter(|s| !s.is_empty())
                .unwrap_or("shell.exec")
                .to_string();
            let raw_args = parts.next().map(str::trim).unwrap_or("");
            let parsed_args = parse_tool_args(raw_args);

            return RouterOutputV1 {
                matched: true,
                confidence: 0.98,
                reasonCodes: vec!["explicit_tool".to_string()],
                needsMemory: false,
                memoryQuery: None,
                toolName: Some(tool_name),
                toolArgs: Some(parsed_args),
                quote: Some("/tool".to_string()),
                policy: Some(RouterPolicyV1 { mustTrigger: true }),
            };
        }

        if input.starts_with("/run ") {
            let command = input.trim_start_matches("/run").trim();
            let args = if command.is_empty() {
                serde_json::json!({})
            } else {
                serde_json::json!({ "command": command })
            };
            return RouterOutputV1 {
                matched: true,
                confidence: 0.95,
                reasonCodes: vec!["explicit_run".to_string()],
                needsMemory: false,
                memoryQuery: None,
                toolName: Some("shell.exec".to_string()),
                toolArgs: Some(args),
                quote: Some("/run".to_string()),
                policy: Some(RouterPolicyV1 { mustTrigger: true }),
            };
        }

        let needs_memory = contains_any(
            input,
            &["记住", "回忆", "memory", "history", "之前", "上次", "刚才"],
        );

        RouterOutputV1 {
            matched: false,
            confidence: if needs_memory { 0.72 } else { 0.32 },
            reasonCodes: vec![if needs_memory {
                "memory_lookup"
            } else {
                "chat_fallback"
            }
            .to_string()],
            needsMemory: needs_memory,
            memoryQuery: if needs_memory {
                Some(input.to_string())
            } else {
                None
            },
            toolName: None,
            toolArgs: None,
            quote: None,
            policy: None,
        }
    }
}

#[derive(Debug, Clone)]
pub struct DefaultMemoryHook {
    max_chars: usize,
}

impl Default for DefaultMemoryHook {
    fn default() -> Self {
        Self { max_chars: 600 }
    }
}

impl DefaultMemoryHook {
    pub fn new(max_chars: usize) -> Self {
        Self {
            max_chars: max_chars.max(1),
        }
    }
}

impl MemoryHook for DefaultMemoryHook {
    fn inject(&self, input: &str) -> String {
        let text = input.trim();
        if text.is_empty() {
            return "memory.injected: <empty>".to_string();
        }

        let mut out = String::with_capacity(self.max_chars + 32);
        let mut count = 0usize;
        for ch in text.chars() {
            if count >= self.max_chars {
                break;
            }
            out.push(ch);
            count += 1;
        }

        if text.chars().count() > self.max_chars {
            out.push('…');
        }

        format!("memory.injected: {out}")
    }
}

#[derive(Debug, Clone, Copy, Default)]
pub struct DefaultCorrectorHook;

impl CorrectorHook for DefaultCorrectorHook {
    fn validate_tool_args(&self, tool_call: &ToolCallIrV1) -> Result<(), String> {
        if tool_call.name.trim().is_empty() {
            return Err("tool name cannot be empty".to_string());
        }
        if !tool_call.args.is_object() {
            return Err("tool args must be JSON object".to_string());
        }
        if let Some(quote) = tool_call.quote.as_deref() {
            if quote.trim().is_empty() {
                return Err("tool quote cannot be blank".to_string());
            }
        }
        Ok(())
    }
}

#[derive(Debug, Clone)]
pub struct EngineTurnResult {
    pub router: RouterOutputV1,
    pub input_for_provider: String,
    pub output: String,
}

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

    pub fn run_turn_with_defaults(&self, user_input: &str) -> Result<EngineTurnResult, String> {
        let router = DefaultRouterHook;

        let router_output = router.route(user_input);
        let input_for_provider = user_input.trim().to_string();

        if input_for_provider.is_empty() {
            return Err("engine input cannot be empty".to_string());
        }

        Ok(EngineTurnResult {
            router: router_output,
            output: input_for_provider.clone(),
            input_for_provider,
        })
    }
}

fn parse_tool_args(raw_args: &str) -> Value {
    if raw_args.is_empty() {
        return serde_json::json!({});
    }

    let parsed = serde_json::from_str::<Value>(raw_args)
        .unwrap_or_else(|_| serde_json::json!({ "raw": raw_args }));

    if parsed.is_object() {
        parsed
    } else {
        serde_json::json!({ "value": parsed })
    }
}

fn contains_any(input: &str, keywords: &[&str]) -> bool {
    let lower = input.to_lowercase();
    keywords
        .iter()
        .any(|keyword| lower.contains(&keyword.to_lowercase()))
}
