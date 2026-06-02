use flate2::{write::DeflateEncoder, Compression};
use serde_json::Value;
use std::{env, fs, io::Write, path::{Path, PathBuf}};

const HEADER_LEN: usize = 128;
const CONTENT_KIND_NEUI: u16 = 32;

fn main() {
    if let Err(err) = run() {
        eprintln!("[ERROR] {err}");
        std::process::exit(1);
    }
}

fn run() -> Result<(), String> {
    let mut root = PathBuf::from(".");
    let mut all = false;
    let mut check = false;
    let mut manifests: Vec<PathBuf> = Vec::new();
    let mut output: Option<PathBuf> = None;
    let mut args = env::args().skip(1).peekable();
    while let Some(arg) = args.next() {
        match arg.as_str() {
            "--root" => root = PathBuf::from(args.next().ok_or("--root requires value")?),
            "--manifest" => manifests.push(PathBuf::from(args.next().ok_or("--manifest requires value")?)),
            "--output" | "-o" => output = Some(PathBuf::from(args.next().ok_or("--output requires value")?)),
            "--all" => all = true,
            "--check" => check = true,
            "--help" | "-h" => { print_help(); return Ok(()); }
            other => return Err(format!("unknown argument '{other}'")),
        }
    }
    if all || manifests.is_empty() {
        manifests.extend(discover_import_manifests(&root)?);
    }
    manifests.sort();
    manifests.dedup();
    if manifests.is_empty() {
        println!("[WARN] no .neui.import.json manifests found");
        return Ok(());
    }
    let mut packed = 0usize;
    for manifest in manifests {
        let manifest_path = absolutize(&root, &manifest);
        let data = read_json(&manifest_path)?;
        let target = output.clone().unwrap_or_else(|| target_path(&root, &data));
        let bytes = build_neui(&root, &data, &manifest_path)?;
        if check {
            println!("[CHECK] {} -> {} bytes={}", rel(&root, &manifest_path), rel(&root, &target), bytes.len());
        } else {
            if let Some(parent) = target.parent() { fs::create_dir_all(parent).map_err(|e| format!("create parent '{}' failed: {e}", parent.display()))?; }
            fs::write(&target, &bytes).map_err(|e| format!("write '{}' failed: {e}", target.display()))?;
            println!("[OK] packed {} -> {} bytes={}", rel(&root, &manifest_path), rel(&root, &target), bytes.len());
        }
        packed += 1;
    }
    println!("[OK] neui packer completed count={packed} check={check}");
    Ok(())
}

fn print_help() {
    println!("northstar-neui-packer --root <repo> [--all|--manifest path] [--output path] [--check]");
}

fn discover_import_manifests(root: &Path) -> Result<Vec<PathBuf>, String> {
    let base = root.join("NewEngine/neocore2/assets/ui");
    let mut out = Vec::new();
    visit(&base, &mut out)?;
    Ok(out)
}

fn visit(path: &Path, out: &mut Vec<PathBuf>) -> Result<(), String> {
    if !path.exists() { return Ok(()); }
    for entry in fs::read_dir(path).map_err(|e| format!("read_dir '{}' failed: {e}", path.display()))? {
        let entry = entry.map_err(|e| e.to_string())?;
        let path = entry.path();
        if path.is_dir() { visit(&path, out)?; }
        else if path.file_name().and_then(|v| v.to_str()).map(|n| n.ends_with(".neui.import.json")).unwrap_or(false) { out.push(path); }
    }
    Ok(())
}

fn absolutize(root: &Path, path: &Path) -> PathBuf {
    if path.is_absolute() { path.to_path_buf() } else { root.join(path) }
}

fn read_json(path: &Path) -> Result<Value, String> {
    let text = fs::read_to_string(path).map_err(|e| format!("read '{}' failed: {e}", path.display()))?;
    serde_json::from_str(&text).map_err(|e| format!("invalid json '{}': {e}", path.display()))
}

fn target_path(root: &Path, data: &Value) -> PathBuf {
    let target = data.get("target_asset").and_then(Value::as_str).unwrap_or("ui/editor/generated.neui");
    let rel = target.trim_start_matches("assets/");
    root.join("NewEngine/neocore2/assets").join(rel)
}

fn build_neui(root: &Path, data: &Value, manifest_path: &Path) -> Result<Vec<u8>, String> {
    let target_asset = data.get("target_asset").and_then(Value::as_str).unwrap_or("ui/editor/generated.neui");
    let logical_path = format!("assets/{}", target_asset.trim_start_matches("assets/"));
    let xml = xmlcentral_for_manifest(data);

    // Runtime .neui must not carry raw JSON inside the asset. The import file is
    // authoring-only; the shipped file is a compact NEF8 envelope with an empty
    // header-metadata range and a deflate-compressed XMLcentral body. Semantic
    // entry/dependency data is recovered by engine.assets.ui from the body and
    // DTO compiler, not by exposing a JSON blob in the binary file.
    let body = xml.as_bytes();
    let body_hash = blake3::hash(body);
    let compressed = deflate(body)?;
    let metadata_offset = 0u64;
    let metadata_len = 0u64;
    let body_offset = HEADER_LEN as u64;
    let body_len = compressed.len() as u64;
    let entry_count = entry_names(data).len().max(1) as u64;

    let mut out = vec![0u8; HEADER_LEN];
    out[0..4].copy_from_slice(b"NEF8");
    write_u16(&mut out, 4, 1);
    write_u16(&mut out, 6, HEADER_LEN as u16);
    write_u16(&mut out, 8, CONTENT_KIND_NEUI);
    write_u16(&mut out, 10, 1);
    write_u16(&mut out, 12, 1);
    write_u64(&mut out, 16, body_offset);
    write_u64(&mut out, 24, body_len);
    write_u64(&mut out, 32, body.len() as u64);
    write_u64(&mut out, 40, entry_count);
    write_u64(&mut out, 48, metadata_offset);
    write_u64(&mut out, 56, metadata_len);
    out[64..96].copy_from_slice(body_hash.as_bytes());
    write_u64(&mut out, 96, stable_u64(&logical_path));
    write_u64(&mut out, 104, stable_u64(&import_settings_hash(data)));
    write_u64(&mut out, 112, 1);
    out.extend_from_slice(&compressed);
    let _ = manifest_path;
    let _ = root;
    Ok(out)
}

fn deflate(bytes: &[u8]) -> Result<Vec<u8>, String> {
    let mut encoder = DeflateEncoder::new(Vec::new(), Compression::default());
    encoder.write_all(bytes).map_err(|e| e.to_string())?;
    encoder.finish().map_err(|e| e.to_string())
}

fn xmlcentral_for_manifest(data: &Value) -> String {
    match data.get("schema").and_then(Value::as_str).unwrap_or("") {
        "newengine.ui_theme.import.v1" => theme_xml(data),
        _ => panel_or_shell_xml(data),
    }
}

fn panel_or_shell_xml(data: &Value) -> String {
    let surface = esc(data.get("surface_id").and_then(Value::as_str).unwrap_or("engine.ui.editor.generated"));
    let label = esc(data.get("label").and_then(Value::as_str).or_else(|| data.get("composition_role").and_then(Value::as_str)).unwrap_or("Editor Panel"));
    let theme = esc(data.get("theme_ref").and_then(Value::as_str).unwrap_or("assets/ui/themes/northstar_editor.neui@editor_light"));
    let data_contract = esc(data.get("data_contract").and_then(Value::as_str).unwrap_or("newengine.ui.generated.v1"));
    let source_gateway = esc(data.get("source_gateway").and_then(Value::as_str).unwrap_or("engine.ui"));
    let entries = entry_names(data);
    let mut xml = String::new();
    xml.push_str("<NeUiDictionary schema=\"newengine.neui.xmlcentral.v1\">\n  <Entries>\n");
    for entry in &entries { xml.push_str(&format!("    <Entry name=\"{}\" kind=\"ui_surface\" />\n", esc(entry))); }
    xml.push_str("  </Entries>\n  <Dependencies>\n");
    xml.push_str(&format!("    <ThemeRef ref=\"{}\" />\n", theme));
    for dep in string_array(data, "component_libraries") { xml.push_str(&format!("    <ComponentRef ref=\"{}\" />\n", esc(&dep))); }
    xml.push_str("  </Dependencies>\n");
    xml.push_str(&format!("  <Surface name=\"{}\" kind=\"editor_panel\" root=\"layout.main\" theme=\"{}\" z_order=\"200\" />\n", surface, theme));
    xml.push_str(&format!("  <Layout name=\"layout.main\" title=\"{}\" role=\"editor_panel\">\n", label));
    xml.push_str(&format!("    <Panel id=\"panel.root\" title=\"{}\" class=\"editor-panel\">\n", label));
    xml.push_str(&format!("      <Text id=\"panel.contract\" text=\"{}\" detail=\"{}\" />\n", data_contract, source_gateway));
    if let Some(menus) = data.get("menus").and_then(Value::as_array) {
        xml.push_str("      <Row id=\"panel.menus\" class=\"toolbar\">\n");
        for menu in menus { xml.push_str(&format!("        <Button id=\"menu.{}\" text=\"{}\" action=\"editor.menu.{}\" />\n", esc(menu.get("id").and_then(Value::as_str).unwrap_or("menu")), esc(menu.get("label").and_then(Value::as_str).unwrap_or("Menu")), esc(menu.get("id").and_then(Value::as_str).unwrap_or("menu")))); }
        xml.push_str("      </Row>\n");
    }
    xml.push_str("    </Panel>\n  </Layout>\n</NeUiDictionary>\n");
    xml
}

fn theme_xml(data: &Value) -> String {
    let theme_id = esc(data.get("theme_id").and_then(Value::as_str).unwrap_or("northstar.editor"));
    let entry = esc(data.get("entry").and_then(Value::as_str).unwrap_or("editor_light"));
    let mut xml = String::new();
    xml.push_str("<NeUiThemeLibrary schema=\"newengine.neui.theme_library.v1\">\n  <Entries>\n");
    xml.push_str(&format!("    <Entry name=\"{}\" kind=\"ui_theme\" />\n", entry));
    xml.push_str("    <Entry name=\"editor_compact\" kind=\"ui_theme\" />\n    <Entry name=\"editor_wide\" kind=\"ui_theme\" />\n  </Entries>\n");
    xml.push_str(&format!("  <Theme name=\"{}\" id=\"{}\" density=\"normal\">\n", entry, theme_id));
    if let Some(metrics) = data.get("metrics").and_then(Value::as_object) { for (k,v) in metrics { xml.push_str(&format!("    <Metric name=\"{}\" value=\"{}\" />\n", esc(k), esc(&v.to_string()))); } }
    if let Some(fonts) = data.get("font_tokens").and_then(Value::as_object) { for (k,v) in fonts { xml.push_str(&format!("    <FontToken name=\"{}\" ref=\"{}\" />\n", esc(k), esc(v.as_str().unwrap_or("")))); } }
    xml.push_str("    <Color name=\"panel.bg\" value=\"#20242CFF\" />\n    <Color name=\"accent\" value=\"#D6A13AFF\" />\n  </Theme>\n</NeUiThemeLibrary>\n");
    xml
}


fn entry_names(data: &Value) -> Vec<String> {
    let mut out = Vec::new();
    if let Some(entry_ref) = data.get("entry_ref").and_then(Value::as_str) {
        if let Some((_, entry)) = entry_ref.rsplit_once('@') { out.push(entry.to_owned()); }
    }
    if let Some(entry) = data.get("entry").and_then(Value::as_str) { out.push(entry.to_owned()); }
    if out.is_empty() { out.push("surface".to_owned()); }
    out.sort(); out.dedup(); out
}


fn string_array(data: &Value, key: &str) -> Vec<String> {
    data.get(key).and_then(Value::as_array).map(|arr| arr.iter().filter_map(Value::as_str).map(ToOwned::to_owned).collect()).unwrap_or_default()
}

fn import_settings_hash(data: &Value) -> String { blake3::hash(data.to_string().as_bytes()).to_hex().to_string()[..16].to_owned() }
fn stable_u64(value: &str) -> u64 { let h=blake3::hash(value.as_bytes()); u64::from_le_bytes(h.as_bytes()[0..8].try_into().unwrap()) }
fn write_u16(out: &mut [u8], offset: usize, value: u16) { out[offset..offset+2].copy_from_slice(&value.to_le_bytes()); }
fn write_u64(out: &mut [u8], offset: usize, value: u64) { out[offset..offset+8].copy_from_slice(&value.to_le_bytes()); }
fn rel(root: &Path, path: &Path) -> String { path.strip_prefix(root).unwrap_or(path).to_string_lossy().replace('\\', "/") }
fn esc(value: &str) -> String { value.replace('&', "&amp;").replace('"', "&quot;").replace('<', "&lt;").replace('>', "&gt;") }
