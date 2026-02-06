fn main() {
    if let Err(err) = bao_dimsum_process::mcp_bridge::run_mcp_bridge_server() {
        eprintln!("{err}");
        std::process::exit(1);
    }
}
