fn main() {
    if let Err(err) = bao_dimsum_process::pipeline_hooks::run_memory_server() {
        eprintln!("{err}");
        std::process::exit(1);
    }
}
