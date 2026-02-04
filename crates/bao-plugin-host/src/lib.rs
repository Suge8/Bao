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
pub struct ModuleCacheKey {
    pub sha256: String,
}

#[derive(Debug, Clone)]
pub struct InstancePoolSpec {
    pub warm_instances: u32,
}

#[derive(Debug, Clone)]
pub struct WasmRuntimeSpec {
    pub entry: String,
    pub performance_tier: PerformanceTier,
    pub limits: WasmLimits,
    pub module_cache: ModuleCacheKey,
    pub instance_pool: Option<InstancePoolSpec>,
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

pub trait WasmModuleCache {
    fn get(&self, key: &ModuleCacheKey) -> Option<Vec<u8>>;
    fn put(&self, key: ModuleCacheKey, serialized_module: Vec<u8>);
}

pub trait WasmInstancePool {
    fn warm_size(&self) -> u32;
}

#[derive(Debug, Clone)]
pub struct PluginHostError {
    pub code: String,
    pub message: String,
}

pub trait WasmLimitsEnforcer {
    fn configure_fuel(&mut self, fuel_per_call: u64);
    fn configure_memory_limit(&mut self, max_linear_memory_bytes: u64);
    fn configure_timeout_ms(&mut self, timeout_ms: u64);
}
