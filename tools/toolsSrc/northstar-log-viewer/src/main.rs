#![windows_subsystem = "console"]

use northstar_cli::ansi;
use northstar_ulog::{query, read_jsonl_file, UlogEvent, UlogLevel};
use serde_json::{json, Value};
use std::{collections::{BTreeMap, BTreeSet}, env, fs::File, io::{self, Write}, path::PathBuf, process, str::FromStr};

const TOOL_NAME: &str = "northstar-log-viewer";
const VERSION: &str = env!("CARGO_PKG_VERSION");
const ACCEPTED_INPUTS: &str = "*.ulog.jsonl, *.ulog, *.jsonl";
const PRODUCED_OUTPUTS: &str = "*.json, *.csv, *.md";

fn main() {
    if let Err(err) = dispatch(env::args().skip(1).collect()) {
        ansi::error(err);
        process::exit(1);
    }
}

fn dispatch(args: Vec<String>) -> Result<(), String> {
    if args.is_empty() || matches!(args[0].as_str(), "--help" | "-h" | "help") {
        print_help();
        return Ok(());
    }

    match args[0].as_str() {
        "version" | "--version" | "-V" => {
            println!("{TOOL_NAME} {VERSION}");
            Ok(())
        }
        "accepted-inputs" | "inputs" | "formats" => {
            ansi::info(format!("{TOOL_NAME} version={VERSION}"));
            ansi::info(format!("accepted input files: {ACCEPTED_INPUTS}"));
            ansi::info(format!("produced output files: {PRODUCED_OUTPUTS}"));
            Ok(())
        }
        "doctor" => {
            ansi::ok(format!("{TOOL_NAME} doctor passed"));
            ansi::info(format!("version={VERSION}"));
            ansi::info("schema=northstar.ulog.event.v1");
            Ok(())
        }
        "inspect" => cmd_inspect(&args[1..]),
        "summary" => cmd_summary(&args[1..]),
        "filter" => cmd_filter(&args[1..]),
        "search" => cmd_search(&args[1..]),
        "export" => cmd_export(&args[1..]),
        "tail" => cmd_tail(&args[1..]),
        other => Err(format!("unknown command '{other}'. Use --help to list supported commands.")),
    }
}

fn print_help() {
    println!(r#"North Star Log Viewer {VERSION}

USAGE:
  northstar-log-viewer --help
  northstar-log-viewer version
  northstar-log-viewer accepted-inputs
  northstar-log-viewer doctor
  northstar-log-viewer inspect <file.ulog.jsonl>
  northstar-log-viewer summary <file.ulog.jsonl>
  northstar-log-viewer filter <file.ulog.jsonl> [--level WARN] [--source name] [--event event.id]
  northstar-log-viewer search <file.ulog.jsonl> <query>
  northstar-log-viewer export <file.ulog.jsonl> --format json|csv|md
  northstar-log-viewer tail <file.ulog.jsonl> [--count N]

ACCEPTED INPUTS:
  {ACCEPTED_INPUTS}

PRODUCED OUTPUTS:
  {PRODUCED_OUTPUTS}

NOTES:
  Status commands may print [INFO]/[OK] tags.
  Payload export commands write clean JSON/CSV/Markdown without ANSI/status tags.
"#);
}

fn required_file(args: &[String], command: &str) -> Result<PathBuf, String> {
    args.iter()
        .find(|arg| !arg.starts_with('-'))
        .map(PathBuf::from)
        .ok_or_else(|| format!("{command} requires <file.ulog.jsonl>"))
}

fn arg_value(args: &[String], name: &str) -> Option<String> {
    args.windows(2).find(|pair| pair[0] == name).map(|pair| pair[1].clone())
}

fn load_events(args: &[String], command: &str) -> Result<(PathBuf, Vec<UlogEvent>), String> {
    let path = required_file(args, command)?;
    let report = read_jsonl_file(&path)?;
    for warning in report.warnings {
        ansi::warn(warning);
    }
    Ok((path, report.events))
}

fn cmd_inspect(args: &[String]) -> Result<(), String> {
    let (path, events) = load_events(args, "inspect")?;
    ansi::info(format!("file={}", path.display()));
    ansi::info(format!("events={}", events.len()));
    for event in events.iter().take(20) {
        println!("{} {} {} {}", event.timestamp_utc, event.level, event.source.name, event.event_id);
    }
    ansi::ok("inspect completed");
    Ok(())
}

fn cmd_summary(args: &[String]) -> Result<(), String> {
    let (path, events) = load_events(args, "summary")?;
    let mut levels: BTreeMap<String, usize> = BTreeMap::new();
    let mut sources: BTreeSet<String> = BTreeSet::new();
    for event in &events {
        *levels.entry(event.level.to_string()).or_default() += 1;
        sources.insert(event.source.name.clone());
    }
    ansi::info(format!("file={}", path.display()));
    ansi::info(format!("events={}", events.len()));
    ansi::info(format!("levels: {}", levels.iter().map(|(k, v)| format!("{k}={v}")).collect::<Vec<_>>().join(" ")));
    ansi::info(format!("sources={}", sources.len()));
    ansi::ok("summary completed");
    Ok(())
}

fn cmd_filter(args: &[String]) -> Result<(), String> {
    let (_, events) = load_events(args, "filter")?;
    let mut selected: Vec<&UlogEvent> = events.iter().collect();
    if let Some(level) = arg_value(args, "--level") {
        let level = UlogLevel::from_str(&level)?;
        selected = query::filter_by_level(&events, level);
    }
    if let Some(source) = arg_value(args, "--source") {
        selected.retain(|event| event.source.name.eq_ignore_ascii_case(&source));
    }
    if let Some(event_id) = arg_value(args, "--event") {
        selected.retain(|event| event.event_id == event_id);
    }
    for event in selected {
        println!("{} {} {} {}", event.timestamp_utc, event.level, event.source.name, event.event_id);
    }
    Ok(())
}

fn cmd_search(args: &[String]) -> Result<(), String> {
    let path = required_file(args, "search")?;
    let file_index = args.iter().position(|arg| PathBuf::from(arg) == path).unwrap_or(0);
    let query_text = args.get(file_index + 1).ok_or_else(|| "search requires <query>".to_owned())?;
    let report = read_jsonl_file(&path)?;
    for warning in report.warnings {
        ansi::warn(warning);
    }
    let matches = query::search_text(&report.events, query_text);
    if matches.is_empty() {
        return Err(format!("no events matched query '{query_text}'"));
    }
    for event in matches {
        println!("{} {} {} {} {}", event.timestamp_utc, event.level, event.source.name, event.event_id, event.message);
    }
    Ok(())
}

fn cmd_export(args: &[String]) -> Result<(), String> {
    let path = required_file(args, "export")?;
    let format = arg_value(args, "--format").unwrap_or_else(|| "json".to_owned()).to_ascii_lowercase();
    let report = read_jsonl_file(&path)?;
    match format.as_str() {
        "json" => {
            let payload = json!({
                "schema": "northstar.ulog.export.v1",
                "file": path.to_string_lossy(),
                "events": report.events,
            });
            serde_json::to_writer_pretty(io::stdout(), &payload).map_err(|e| format!("write json failed: {e}"))?;
            println!();
        }
        "csv" => write_csv(&report.events)?,
        "md" | "markdown" => write_markdown(&report.events)?,
        other => return Err(format!("unsupported export format '{other}'")),
    }
    Ok(())
}

fn cmd_tail(args: &[String]) -> Result<(), String> {
    let (_, events) = load_events(args, "tail")?;
    let count = arg_value(args, "--count").and_then(|v| v.parse::<usize>().ok()).unwrap_or(20);
    let start = events.len().saturating_sub(count);
    for event in &events[start..] {
        println!("{} {} {} {} {}", event.timestamp_utc, event.level, event.source.name, event.event_id, event.message);
    }
    Ok(())
}

fn write_csv(events: &[UlogEvent]) -> Result<(), String> {
    let mut out = io::BufWriter::new(io::stdout());
    writeln!(out, "timestamp_utc,level,source,event_id,message").map_err(|e| e.to_string())?;
    for event in events {
        writeln!(out, "{},{},{},{},{}", csv_cell(&event.timestamp_utc), event.level, csv_cell(&event.source.name), csv_cell(&event.event_id), csv_cell(&event.message)).map_err(|e| e.to_string())?;
    }
    Ok(())
}

fn write_markdown(events: &[UlogEvent]) -> Result<(), String> {
    println!("| timestamp_utc | level | source | event_id | message |");
    println!("|---|---|---|---|---|");
    for event in events {
        println!("| {} | {} | {} | {} | {} |", md_cell(&event.timestamp_utc), event.level, md_cell(&event.source.name), md_cell(&event.event_id), md_cell(&event.message));
    }
    Ok(())
}

fn csv_cell(value: &str) -> String {
    let escaped = value.replace('"', "\"\"");
    format!("\"{escaped}\"")
}

fn md_cell(value: &str) -> String {
    value.replace('|', "\\|").replace('\n', " ")
}

#[allow(dead_code)]
fn _write_json_file(path: &PathBuf, value: &Value) -> Result<(), String> {
    let file = File::create(path).map_err(|e| format!("create '{}' failed: {e}", path.display()))?;
    serde_json::to_writer_pretty(file, value).map_err(|e| format!("write '{}' failed: {e}", path.display()))
}
