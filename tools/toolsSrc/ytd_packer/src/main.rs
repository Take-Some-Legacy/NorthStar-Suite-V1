mod args;
mod commands;
mod fixture_gen;
mod help;
mod nef8;
mod texture_io;
mod texture_sources;

fn main() {
    if let Err(err) = commands::dispatch(std::env::args().skip(1).collect()) {
        eprintln!("[ERROR] {err}");
        std::process::exit(1);
    }
}
