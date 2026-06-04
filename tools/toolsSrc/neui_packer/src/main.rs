mod args;
mod commands;
mod diagnostics;
mod discovery;
mod help;

fn main() {
    if let Err(err) = commands::dispatch(std::env::args().skip(1).collect()) {
        eprintln!("[ERROR] {err}");
        std::process::exit(1);
    }
}
