// Phase0/1: WebSocket Gateway interface placeholder.
// Desktop runs the gateway; mobile connects over LAN/tunnel.

#[derive(Debug, Clone)]
pub struct GatewayConfig {
    pub bind_addr: String,
    pub port: u16,
}

#[derive(Debug, Clone)]
pub struct GatewayHello {
    pub bao_core_version: String,
    pub device_id: String,
    pub last_event_id: Option<i64>,
}

#[derive(Debug, Clone)]
pub struct GatewayWelcome {
    pub session: String,
    pub assigned_device_id: String,
    pub replay_from_event_id: Option<i64>,
}

pub trait Gateway {
    fn start(&self, cfg: GatewayConfig) -> Result<(), String>;
    fn stop(&self) -> Result<(), String>;
}
