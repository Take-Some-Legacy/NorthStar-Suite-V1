use std::fs;

use northstar_neui_packer::{
    binding_plan_projection_json, compiled_document_projection_json, dependencies, entry_names,
    inspect_nef8_json, manifest_json_for_xmlcentral, pack_xmlcentral_to_nef8, validate_xmlcentral,
};

use crate::{args::{parse_args, required_input}, discovery, help};

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
        "compile" | "build" | "pack" => run_compile(&raw_args[1..]),
        "inspect" => run_inspect(&raw_args[1..]),
        "validate" => run_validate(&raw_args[1..]),
        "manifest" => run_manifest(&raw_args[1..]),
        "dump-xmlcentral" | "dump-xml" => run_dump_xmlcentral(&raw_args[1..]),
        "dump-compiled-document" => run_dump_compiled_document(&raw_args[1..]),
        "dump-binding-plan" => run_dump_binding_plan(&raw_args[1..]),
        "dump-dependencies" => run_dump_dependencies(&raw_args[1..]),
        "help" | "--help" | "-h" => {
            help::print_help();
            help::wait_for_enter();
            Ok(())
        }
        other if other.starts_with('-') => run_compile(&raw_args),
        other => Err(format!("unknown command '{other}'. Use --help to list supported commands.")),
    }
}

fn run_compile(args: &[String]) -> Result<(), String> {
    let cfg = parse_or_help(args)?;
    let root = cfg.root;
    let mut xml_sources = Vec::new();
    if let Some(input) = cfg.input { xml_sources.push(input); }
    if cfg.all || xml_sources.is_empty() {
        xml_sources.extend(discovery::discover_xml_sources(&root)?);
    }
    xml_sources.sort();
    xml_sources.dedup();
    if xml_sources.is_empty() {
        println!("[WARN] no .neui.xml sources found");
        return Ok(());
    }

    println!("[INFO] UI build started");
    for source in &xml_sources {
        let source_path = discovery::absolutize(&root, source);
        let target = cfg.output.clone().unwrap_or_else(|| discovery::target_path_for_xml(&root, &source_path));
        let xml = fs::read_to_string(&source_path).map_err(|e| format!("read '{}' failed: {e}", source_path.display()))?;
        for warning in validate_xmlcentral(&xml, &discovery::rel(&root, &source_path))? {
            println!("[WARN] {}: {}", discovery::rel(&root, &source_path), warning);
        }
        let logical_path = cfg.logical_path.clone().unwrap_or_else(|| discovery::logical_asset_path_for_output(&root, &target));
        let bytes = pack_xmlcentral_to_nef8(&xml, &logical_path, &discovery::rel(&root, &source_path), entry_names(&xml).len() as u64)?;
        discovery::emit_or_write(&root, &source_path, &target, &bytes, cfg.check)?;
    }
    println!("[OK] UI build completed compiled={} check={}", xml_sources.len(), cfg.check);
    Ok(())
}

fn run_inspect(args: &[String]) -> Result<(), String> {
    let cfg = parse_or_help(args)?;
    let input = required_input(&cfg)?;
    let bytes = fs::read(&input).map_err(|e| format!("read '{}' failed: {e}", input.display()))?;
    let value = inspect_nef8_json(&bytes)?;
    println!("{}", serde_json::to_string_pretty(&value).map_err(|e| e.to_string())?);
    Ok(())
}

fn run_validate(args: &[String]) -> Result<(), String> {
    let cfg = parse_or_help(args)?;
    let root = cfg.root;
    let mut inputs = Vec::new();
    if let Some(input) = cfg.input { inputs.push(input); }
    if cfg.all || inputs.is_empty() {
        inputs.extend(discovery::discover_xml_sources(&root)?);
        inputs.extend(discovery::discover_neui_assets(&root)?);
    }
    inputs.sort();
    inputs.dedup();
    if inputs.is_empty() {
        println!("[WARN] no .neui.xml or .neui assets found");
        return Ok(());
    }
    let mut surfaces = 0usize;
    let mut themes = 0usize;
    let mut component_libraries = 0usize;
    for input in inputs {
        let path = discovery::absolutize(&root, &input);
        let xml = discovery::read_xml_or_nef8(&path)?;
        for warning in validate_xmlcentral(&xml, &discovery::rel(&root, &path))? {
            println!("[WARN] {}: {}", discovery::rel(&root, &path), warning);
        }
        surfaces += discovery::count_tag(&xml, "Surface");
        themes += discovery::count_tag(&xml, "Theme");
        component_libraries += discovery::count_tag(&xml, "ComponentTemplate");
        println!("[OK] validated: {}", discovery::rel(&root, &path));
    }
    println!("[OK] validated: {surfaces} surface(s), {themes} theme(s), {component_libraries} component librar(y/ies)");
    Ok(())
}

fn run_manifest(args: &[String]) -> Result<(), String> {
    let cfg = parse_or_help(args)?;
    let input = required_input(&cfg)?;
    let xml = discovery::read_xml_or_nef8(&input)?;
    let logical = cfg.logical_path.unwrap_or_else(|| discovery::logical_asset_path_for_output(&cfg.root, &input));
    discovery::write_or_print_json(cfg.output.as_deref(), &manifest_json_for_xmlcentral(&xml, &logical)?)
}

fn run_dump_xmlcentral(args: &[String]) -> Result<(), String> {
    let cfg = parse_or_help(args)?;
    let input = required_input(&cfg)?;
    let xml = discovery::read_xml_or_nef8(&input)?;
    if let Some(output) = cfg.output {
        if let Some(parent) = output.parent() { fs::create_dir_all(parent).map_err(|e| e.to_string())?; }
        fs::write(&output, xml.as_bytes()).map_err(|e| format!("write '{}' failed: {e}", output.display()))?;
        println!("[OK] XMLcentral dumped: {}", output.display());
    } else {
        print!("{xml}");
    }
    Ok(())
}

fn run_dump_compiled_document(args: &[String]) -> Result<(), String> {
    let cfg = parse_or_help(args)?;
    let input = required_input(&cfg)?;
    let xml = discovery::read_xml_or_nef8(&input)?;
    let logical = cfg.logical_path.unwrap_or_else(|| discovery::logical_asset_path_for_output(&cfg.root, &input));
    discovery::write_or_print_json(cfg.output.as_deref(), &compiled_document_projection_json(&xml, &logical)?)
}

fn run_dump_binding_plan(args: &[String]) -> Result<(), String> {
    let cfg = parse_or_help(args)?;
    let input = required_input(&cfg)?;
    let xml = discovery::read_xml_or_nef8(&input)?;
    discovery::write_or_print_json(cfg.output.as_deref(), &binding_plan_projection_json(&xml))
}

fn run_dump_dependencies(args: &[String]) -> Result<(), String> {
    let cfg = parse_or_help(args)?;
    let input = required_input(&cfg)?;
    let xml = discovery::read_xml_or_nef8(&input)?;
    let value = serde_json::json!({
        "schema": "northstar.neui.dependencies.v1",
        "input": input.to_string_lossy(),
        "dependencies": dependencies(&xml),
    });
    discovery::write_or_print_json(cfg.output.as_deref(), &value)
}

fn parse_or_help(args: &[String]) -> Result<crate::args::CommonArgs, String> {
    parse_args(args)
}
