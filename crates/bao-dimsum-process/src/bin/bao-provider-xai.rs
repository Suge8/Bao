fn main() {
    if let Err(err) = bao_dimsum_process::provider::run_provider_server(
        bao_dimsum_process::provider::ProviderKind::XAi,
    ) {
        eprintln!("{err}");
        std::process::exit(1);
    }
}
