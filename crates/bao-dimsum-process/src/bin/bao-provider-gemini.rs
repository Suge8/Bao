fn main() {
    if let Err(err) = bao_dimsum_process::provider::run_provider_server(
        bao_dimsum_process::provider::ProviderKind::Gemini,
    ) {
        eprintln!("{err}");
        std::process::exit(1);
    }
}
