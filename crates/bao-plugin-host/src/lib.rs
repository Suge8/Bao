// Phase0: stubs for WASM/Process plugin host.

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RuntimeKind {
    Wasm,
    Process,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PerformanceTier {
    HighFrequency,
    LowFrequency,
}

#[derive(Debug, Clone)]
pub struct WasmLimits {
    pub max_linear_memory_bytes: u64,
    pub fuel_per_call: u64,
    pub timeout_ms: u64,
}

#[derive(Debug, Clone)]
pub struct WasmRuntimeSpec {
    pub entry: String,
    pub performance_tier: PerformanceTier,
    pub limits: WasmLimits,
}

#[derive(Debug, Clone)]
pub struct ProcessRuntimeSpec {
    pub command: String,
    pub args: Vec<String>,
    pub protocol: String,
}

#[derive(Debug, Clone)]
pub struct PluginRuntimeSpec {
    pub kind: RuntimeKind,
    pub wasm: Option<WasmRuntimeSpec>,
    pub process: Option<ProcessRuntimeSpec>,
}

pub trait PluginHost {
    fn runtime_kind(&self) -> RuntimeKind;
}
