fn main() {
    if let Err(err) = bao_dimsum_process::skills::run_skills_server() {
        eprintln!("{err}");
        std::process::exit(1);
    }
}
