pub fn print_contract(tool_name: &str, accepted_inputs: &str, produced_outputs: &str) {
    println!("[INFO] {tool_name} version={}", env!("CARGO_PKG_VERSION"));
    println!("[INFO] production output: compact [INFO]/[OK]/[WARN]/[ERROR] lines for suite logs");
    println!("[INFO] debug output: add --debug or --verbose to print accepted formats, resolved paths and counts");
    println!("[INFO] accepted input files: {accepted_inputs}");
    println!("[INFO] produced output files: {produced_outputs}");
}

pub fn print_version(tool_name: &str) {
    println!("{tool_name} {}", env!("CARGO_PKG_VERSION"));
}

pub fn print_operation(tool_name: &str, command: &str, debug: bool, accepted_inputs: &str, produced_outputs: &str) {
    let mode = if debug { "debug" } else { "prod" };
    println!("[INFO] {tool_name}: command={command} output_mode={mode}");
    println!("[INFO] accepted input files: {accepted_inputs}");
    println!("[INFO] produced output files: {produced_outputs}");
    if debug {
        println!("[DEBUG] {tool_name}: debug diagnostics enabled");
    }
}

pub fn print_debug_value<T: std::fmt::Display>(debug: bool, key: &str, value: T) {
    if debug {
        println!("[DEBUG] {key}={value}");
    }
}
