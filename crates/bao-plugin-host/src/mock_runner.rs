use std::collections::HashSet;
use std::sync::{Arc, Mutex};

use serde_json::Value;

use crate::{PluginHostError, ToolRunResult, ToolRunner};

#[derive(Clone, Default)]
pub struct MockToolRunner {
    killed_groups: Arc<Mutex<HashSet<String>>>,
}

impl MockToolRunner {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn is_killed(&self, group: &str) -> bool {
        self.killed_groups
            .lock()
            .expect("killed_groups mutex poisoned")
            .contains(group)
    }
}

impl ToolRunner for MockToolRunner {
    fn run_tool(&self, _dimsum_id: &str, tool_name: &str, args: &Value) -> Result<ToolRunResult, PluginHostError> {
        Ok(ToolRunResult {
            ok: true,
            output: serde_json::json!({"tool": tool_name, "args": args}),
        })
    }

    fn kill_group(&self, group: &str) {
        self.killed_groups
            .lock()
            .expect("killed_groups mutex poisoned")
            .insert(group.to_string());
    }
}
