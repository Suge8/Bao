fn main() {
    if let Err(err) = bao_dimsum_process::pipeline_hooks::run_router_server() {
        eprintln!("{err}");
        std::process::exit(1);
    }
}
