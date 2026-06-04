use std::fs;
use crate::diagnostics;

use crate::{
    args::{parse_args, required_input, required_output},
    fswalk,
    help,
    nepak,
};


const TOOL_NAME: &str = "northstar-nepak-packer";
const ACCEPTED_INPUTS: &str = "directory trees and opaque loose files for pack; *.nepak for inspect/validate/extract";
const PRODUCED_OUTPUTS: &str = "*.nepak VFS container; extracted directory trees";

pub fn dispatch(raw_args: Vec<String>) -> Result<(), String> {
    if raw_args.is_empty() {
        help::print_help();
        help::wait_for_enter();
        return Ok(());
    }
    if raw_args.iter().skip(1).any(|it| it == "--help" || it == "-h") {
        help::print_help();
        help::wait_for_enter();
        return Ok(());
    }
    match raw_args[0].as_str() {
        "pack" | "build" | "create" => run_pack(&raw_args[1..]),
        "extract" | "unpack" => run_extract(&raw_args[1..]),
        "inspect" | "parse" => run_inspect(&raw_args[1..]),
        "validate" | "doctor" => run_validate(&raw_args[1..]),
        "accepted-inputs" | "inputs" | "formats" => {
            diagnostics::print_contract(TOOL_NAME, ACCEPTED_INPUTS, PRODUCED_OUTPUTS);
            Ok(())
        }
        "version" | "--version" | "-V" => {
            diagnostics::print_version(TOOL_NAME);
            Ok(())
        }
        "help" | "--help" | "-h" => {
            help::print_help();
            help::wait_for_enter();
            Ok(())
        }
        other => Err(format!("unknown command '{other}'. Use --help to list supported commands.")),
    }
}

fn run_pack(args: &[String]) -> Result<(), String> {
    let cfg = parse_args(args)?;
    let input = required_input(&cfg, "pack")?;
    let output = required_output(&cfg, "pack")?;
    let sources = fswalk::collect_sources(&input)?;
    diagnostics::print_operation(TOOL_NAME, "pack", cfg.debug, ACCEPTED_INPUTS, PRODUCED_OUTPUTS);
    diagnostics::print_debug_value(cfg.debug, "input", input.display());
    diagnostics::print_debug_value(cfg.debug, "output", output.display());
    diagnostics::print_debug_value(cfg.debug, "source_count", sources.len());
    nepak::pack_sources(&sources, &output, !cfg.no_compress)?;
    println!("[OK] built NEPAK package: {} entries={}", output.display(), sources.len());
    Ok(())
}

fn run_extract(args: &[String]) -> Result<(), String> {
    let cfg = parse_args(args)?;
    let input = required_input(&cfg, "extract")?;
    let output = required_output(&cfg, "extract")?;
    let bytes = fs::read(&input).map_err(|e| format!("read '{}' failed: {e}", input.display()))?;
    let count = nepak::extract_to(&bytes, &output, cfg.path.as_deref(), cfg.overwrite)?;
    println!("[OK] extracted NEPAK package: {} entries={} output={}", input.display(), count, output.display());
    Ok(())
}

fn run_inspect(args: &[String]) -> Result<(), String> {
    let cfg = parse_args(args)?;
    let input = required_input(&cfg, "inspect")?;
    let bytes = fs::read(&input).map_err(|e| format!("read '{}' failed: {e}", input.display()))?;
    let value = nepak::inspect_json(&bytes, &input)?;
    println!("{}", serde_json::to_string_pretty(&value).map_err(|e| e.to_string())?);
    Ok(())
}

fn run_validate(args: &[String]) -> Result<(), String> {
    let cfg = parse_args(args)?;
    let input = required_input(&cfg, "validate")?;
    let bytes = fs::read(&input).map_err(|e| format!("read '{}' failed: {e}", input.display()))?;
    let count = nepak::validate_bytes(&bytes)?;
    println!("[OK] validated NEPAK package: {} entries={}", input.display(), count);
    Ok(())
}
