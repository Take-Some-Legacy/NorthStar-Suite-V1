pub const RESET: &str = "\x1b[0m";
pub const GREY: &str = "\x1b[90m";
pub const BLUE: &str = "\x1b[94m";
pub const GREEN: &str = "\x1b[92m";
pub const YELLOW: &str = "\x1b[93m";
pub const RED: &str = "\x1b[91m";

pub fn tag(status: &str) -> String {
    let color = match status {
        "INFO" => BLUE,
        "OK" => GREEN,
        "WARN" => YELLOW,
        "ERROR" => RED,
        _ => RESET,
    };
    format!("{GREY}[{color}{status}{GREY}]{RESET}")
}

pub fn status(status: &str, message: impl AsRef<str>) -> String {
    format!("{} {}", tag(status), message.as_ref())
}

pub fn info(message: impl AsRef<str>) { println!("{}", status("INFO", message)); }
pub fn ok(message: impl AsRef<str>) { println!("{}", status("OK", message)); }
pub fn warn(message: impl AsRef<str>) { println!("{}", status("WARN", message)); }
pub fn error(message: impl AsRef<str>) { eprintln!("{}", status("ERROR", message)); }
