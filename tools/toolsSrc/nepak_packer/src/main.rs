fn main() {
    if let Err(err) = northstar_nepak_packer::commands::dispatch(std::env::args().skip(1).collect()) {
        eprintln!("[ERROR] {err}");
        std::process::exit(1);
    }
}
