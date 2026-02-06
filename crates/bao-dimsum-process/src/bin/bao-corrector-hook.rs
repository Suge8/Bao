fn main() {
    if let Err(err) = bao_dimsum_process::pipeline_hooks::run_corrector_server() {
        eprintln!("{err}");
        std::process::exit(1);
    }
}
