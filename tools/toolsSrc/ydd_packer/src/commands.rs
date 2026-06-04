use std::fs;
use std::path::{Path, PathBuf};
use crate::diagnostics;

use crate::{args::{parse_args, required_input, required_output, required_sources}, help, model, nef8};


const TOOL_NAME: &str = "northstar-ydd-packer";
const ACCEPTED_INPUTS: &str = "*.obj, *.gltf, *.glb, ASCII *.fbx model sources; *.ydd for inspect/list/validate/dump-body";
const PRODUCED_OUTPUTS: &str = "*.ydd runtime NEF8 drawable dictionary; *.yddbody body dumps";

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
        "pack" | "build" | "import" | "create" => run_pack(&raw_args[1..]),
        "inspect" | "parse" => run_inspect(&raw_args[1..]),
        "list" => run_list(&raw_args[1..]),
        "validate" | "doctor" => run_validate(&raw_args[1..]),
        "dump-body" => run_dump_body(&raw_args[1..]),
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
    let sources = required_sources(&cfg, "pack")?;
    let output = required_output(&cfg, "pack", "file.ydd")?;
    diagnostics::print_operation(TOOL_NAME, "pack", cfg.debug, ACCEPTED_INPUTS, PRODUCED_OUTPUTS);
    diagnostics::print_debug_value(cfg.debug, "source_count", sources.len());
    for source in &sources { diagnostics::print_debug_value(cfg.debug, "source", source.display()); }
    diagnostics::print_debug_value(cfg.debug, "output", output.display());
    let import_options = model::ImportOptions::from(&cfg);
    let dictionary = model::import_sources(&sources, &import_options)?;
    let logical = nef8::normalize_logical_path(&output.to_string_lossy());
    let bytes = nef8::pack_ydd(&dictionary, &logical)?;
    write_bytes(&output, &bytes)?;
    println!("[OK] built resident YDD NEF8 ListFile: {} models={}", output.display(), dictionary.models.len());
    for model in &dictionary.models {
        println!("[OK] entry {}@{} meshes={}", logical, model.name, model.meshes.len());
    }
    Ok(())
}

fn run_inspect(args: &[String]) -> Result<(), String> {
    let cfg = parse_args(args)?;
    let input = required_input(&cfg, "inspect")?;
    let bytes = fs::read(&input).map_err(|e| format!("read '{}' failed: {e}", input.display()))?;
    let value = nef8::inspect_json(&bytes, &input.to_string_lossy())?;
    println!("{}", serde_json::to_string_pretty(&value).map_err(|e| e.to_string())?);
    Ok(())
}

fn run_list(args: &[String]) -> Result<(), String> {
    let cfg = parse_args(args)?;
    let input = required_input(&cfg, "list")?;
    let bytes = fs::read(&input).map_err(|e| format!("read '{}' failed: {e}", input.display()))?;
    let parsed = nef8::parse_ydd(&bytes, &input.to_string_lossy())?;
    for entry in parsed.entries { println!("{}", entry.selector); }
    Ok(())
}

fn run_validate(args: &[String]) -> Result<(), String> {
    let cfg = parse_args(args)?;
    let input = required_input(&cfg, "validate")?;
    let bytes = fs::read(&input).map_err(|e| format!("read '{}' failed: {e}", input.display()))?;
    let parsed = nef8::parse_ydd(&bytes, &input.to_string_lossy())?;
    println!("[OK] validated resident YDD NEF8 ListFile: {} models={}", input.display(), parsed.entries.len());
    Ok(())
}

fn run_dump_body(args: &[String]) -> Result<(), String> {
    let cfg = parse_args(args)?;
    let input = required_input(&cfg, "dump-body")?;
    let output = required_output(&cfg, "dump-body", "file.yddbody")?;
    let bytes = fs::read(&input).map_err(|e| format!("read '{}' failed: {e}", input.display()))?;
    let header = nef8::parse_header(&bytes)?;
    let body = nef8::decode_body(&bytes, &header)?;
    write_bytes(&output, &body)?;
    println!("[OK] dumped resident drawable_dictionary body: {}", output.display());
    Ok(())
}

fn write_bytes(output: &Path, bytes: &[u8]) -> Result<(), String> {
    if let Some(parent) = output.parent() {
        if !parent.as_os_str().is_empty() { fs::create_dir_all(parent).map_err(|e| format!("create parent '{}' failed: {e}", parent.display()))?; }
    }
    fs::write(output, bytes).map_err(|e| format!("write '{}' failed: {e}", output.display()))
}

#[allow(dead_code)]
fn logical_asset_path(root: &Path, path: &Path) -> String {
    let absolute = if path.is_absolute() { PathBuf::from(path) } else { root.join(path) };
    let rel = absolute.strip_prefix(root).unwrap_or(&absolute);
    nef8::normalize_logical_path(&rel.to_string_lossy())
}
