mod args;
mod commands;
mod help;
mod material;
mod nef8;

fn main() {
    if let Err(err) = commands::dispatch(std::env::args().skip(1).collect()) {
        eprintln!("[ERROR] {err}");
        std::process::exit(1);
    }
}
