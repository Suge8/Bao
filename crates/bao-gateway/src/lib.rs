// Phase0: WebSocket Gateway interface placeholder.

pub trait Gateway {
    fn start(&self) -> Result<(), String>;
}
