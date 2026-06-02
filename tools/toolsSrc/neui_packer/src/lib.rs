use flate2::{read::DeflateDecoder, write::DeflateEncoder, Compression};
use serde_json::{json, Value};
use std::io::{Read, Write};

pub const HEADER_LEN: usize = 128;
pub const CONTENT_KIND_NEUI: u16 = 32;
const LIST_FILE_FLAG_BODY_DEFLATE: u16 = 0x0001;
const LIST_FILE_COMPRESSION_DEFLATE: u16 = 1;

pub fn pack_xmlcentral_to_nef8(
    xmlcentral: &str,
    logical_path: &str,
    import_settings_seed: &str,
    requested_entry_count: u64,
) -> Result<Vec<u8>, String> {
    let diagnostics = validate_xmlcentral(xmlcentral, logical_path)?;
    let _ = diagnostics;
    let body = xmlcentral.as_bytes();
    let body_hash = blake3::hash(body);
    let compressed = deflate(body)?;
    let logical_path = normalize_logical_path(logical_path);
    let entry_count = requested_entry_count.max(entry_names(xmlcentral).len() as u64).max(1);

    let mut out = vec![0u8; HEADER_LEN];
    out[0..4].copy_from_slice(b"NEF8");
    write_u16(&mut out, 4, 1);
    write_u16(&mut out, 6, HEADER_LEN as u16);
    write_u16(&mut out, 8, CONTENT_KIND_NEUI);
    write_u16(&mut out, 10, LIST_FILE_FLAG_BODY_DEFLATE);
    write_u16(&mut out, 12, LIST_FILE_COMPRESSION_DEFLATE);
    write_u64(&mut out, 16, HEADER_LEN as u64);
    write_u64(&mut out, 24, compressed.len() as u64);
    write_u64(&mut out, 32, body.len() as u64);
    write_u64(&mut out, 40, entry_count);
    write_u64(&mut out, 48, 0);
    write_u64(&mut out, 56, 0);
    out[64..96].copy_from_slice(body_hash.as_bytes());
    write_u64(&mut out, 96, stable_u64(&logical_path));
    write_u64(&mut out, 104, stable_u64(import_settings_seed));
    write_u64(&mut out, 112, 1);
    out.extend_from_slice(&compressed);
    Ok(out)
}

pub fn decode_nef8_xmlcentral(bytes: &[u8]) -> Result<String, String> {
    let header = parse_header(bytes)?;
    if header.content_kind != CONTENT_KIND_NEUI {
        return Err(format!(
            "NEF8 content_kind={} is not ui_dictionary ({})",
            header.content_kind, CONTENT_KIND_NEUI
        ));
    }
    if header.compression != LIST_FILE_COMPRESSION_DEFLATE || (header.flags & LIST_FILE_FLAG_BODY_DEFLATE) == 0 {
        return Err(format!(
            "NEF8 .neui requires deflate body flags=0x{:04x} compression={}",
            header.flags, header.compression
        ));
    }
    let start = header.body_offset as usize;
    let end = start.saturating_add(header.body_len as usize);
    let compressed = bytes.get(start..end).ok_or_else(|| {
        format!(
            "NEF8 body range is outside file body_offset={} body_len={} file_len={}",
            header.body_offset,
            header.body_len,
            bytes.len()
        )
    })?;
    let inflated = inflate(compressed)?;
    if inflated.len() as u64 != header.body_uncompressed_len {
        return Err(format!(
            "NEF8 inflated body size mismatch actual={} expected={}",
            inflated.len(), header.body_uncompressed_len
        ));
    }
    let hash = blake3::hash(&inflated);
    if hash.as_bytes() != &header.body_raw_hash {
        return Err("NEF8 body hash mismatch after inflate".to_owned());
    }
    String::from_utf8(inflated).map_err(|e| format!(".neui XMLcentral body is not UTF-8: {e}"))
}

pub fn inspect_nef8_json(bytes: &[u8]) -> Result<Value, String> {
    let header = parse_header(bytes)?;
    let xmlcentral = if header.content_kind == CONTENT_KIND_NEUI {
        Some(decode_nef8_xmlcentral(bytes)?)
    } else {
        None
    };
    let summary = xmlcentral
        .as_deref()
        .map(xmlcentral_summary_json)
        .unwrap_or_else(|| json!({}));
    Ok(json!({
        "schema": "northstar.neui.inspect.v1",
        "ok": header.content_kind == CONTENT_KIND_NEUI,
        "header": {
            "magic": "NEF8",
            "version": header.version,
            "header_len": header.header_len,
            "content_kind": header.content_kind,
            "content_kind_label": if header.content_kind == CONTENT_KIND_NEUI { "ui_dictionary" } else { "non_ui_dictionary" },
            "flags": header.flags,
            "compression": header.compression,
            "entry_count": header.entry_count,
            "body_offset": header.body_offset,
            "body_len": header.body_len,
            "body_uncompressed_len": header.body_uncompressed_len,
            "stable_file_id": format!("{:016x}", header.stable_file_id),
        },
        "xmlcentral": summary,
    }))
}

pub fn manifest_json_for_xmlcentral(xmlcentral: &str, logical_path: &str) -> Result<Value, String> {
    validate_xmlcentral(xmlcentral, logical_path)?;
    let entries = entry_names(xmlcentral);
    let deps = dependencies(xmlcentral);
    Ok(json!({
        "schema": "asset.inspect.neui.v1",
        "source": normalize_logical_path(logical_path),
        "asset_kind": "ui_dictionary",
        "container": "newengine.listfile.nef8.neui",
        "semantic_gateway": "engine.assets.ui",
        "runtime_gateway": "engine.ui",
        "entries": entries.iter().map(|entry| json!({
            "name": entry,
            "entry_ref": format!("{}@{}", normalize_logical_path(logical_path), entry),
            "asset_kind": "ui_surface_or_library",
            "route": {
                "gateway": "engine.assets.ui",
                "method": "assets.ui.compile_document_v1",
                "semantic_owner": "ui_dictionary"
            }
        })).collect::<Vec<_>>(),
        "dependencies": deps,
        "summary": xmlcentral_summary_json(xmlcentral),
    }))
}

pub fn compiled_document_projection_json(xmlcentral: &str, logical_path: &str) -> Result<Value, String> {
    validate_xmlcentral(xmlcentral, logical_path)?;
    let surface_id = first_attr_value(xmlcentral, "Surface", "name").unwrap_or_else(|| "engine.ui.surface".to_owned());
    let root_id = first_attr_value(xmlcentral, "Surface", "root").unwrap_or_else(|| "layout.main".to_owned());
    let theme_ref = first_attr_value(xmlcentral, "Surface", "theme");
    Ok(json!({
        "schema": "newengine.ui.compiled_document.projection.v1",
        "note": "diagnostic projection; authoritative runtime compilation is owned by engine.assets.ui",
        "document_ref": normalize_logical_path(logical_path),
        "surface_id": surface_id,
        "root_id": root_id,
        "theme_ref": theme_ref,
        "dependencies": dependencies(xmlcentral),
        "binding_plan": binding_plan_projection_json(xmlcentral),
        "source": {
            "kind": "asset",
            "document_ref": normalize_logical_path(logical_path)
        },
        "xmlcentral_summary": xmlcentral_summary_json(xmlcentral),
    }))
}

pub fn binding_plan_projection_json(xmlcentral: &str) -> Value {
    let binding_count = count_open_tags(xmlcentral, "Binding");
    let event_count = count_open_tags(xmlcentral, "Event");
    json!({
        "schema": "newengine.ui.binding_plan.projection.v1",
        "source": "XMLcentral",
        "binding_count": binding_count,
        "event_count": event_count,
        "policy": "bindings/events are authored in XML and compiled by engine.assets.ui into UiBindingPlan/UiActionEdge DTOs"
    })
}

pub fn xmlcentral_summary_json(xmlcentral: &str) -> Value {
    json!({
        "root": root_name(xmlcentral).unwrap_or_else(|| "<unknown>".to_owned()),
        "entries": entry_names(xmlcentral),
        "dependencies": dependencies(xmlcentral),
        "surface_count": count_open_tags(xmlcentral, "Surface"),
        "layout_count": count_open_tags(xmlcentral, "Layout"),
        "theme_count": count_open_tags(xmlcentral, "Theme"),
        "component_template_count": count_open_tags(xmlcentral, "ComponentTemplate"),
        "binding_count": count_open_tags(xmlcentral, "Binding"),
        "event_count": count_open_tags(xmlcentral, "Event"),
    })
}

pub fn validate_xmlcentral(xmlcentral: &str, source_ref: &str) -> Result<Vec<String>, String> {
    let root = root_name(xmlcentral).ok_or_else(|| format!("{source_ref}: XML document has no root element"))?;
    let mut warnings = Vec::new();
    match root.as_str() {
        "NeUiDictionary" => {
            if count_open_tags(xmlcentral, "Surface") == 0 {
                warnings.push("NeUiDictionary has no <Surface>; it can be packed but engine.assets.ui cannot mount it as a live surface until one is authored".to_owned());
            }
        }
        "NeUiThemeLibrary" => {
            if count_open_tags(xmlcentral, "Theme") == 0 {
                warnings.push("NeUiThemeLibrary has no <Theme>; it can be packed as XML data but exposes no theme entries".to_owned());
            }
        }
        other => warnings.push(format!(
            "generic XML root '{other}' accepted for NEF8/ListFile storage; runtime UI compilation expects NeUiDictionary or NeUiThemeLibrary"
        )),
    }
    if entry_names(xmlcentral).is_empty() {
        warnings.push("no <Entry> tags found; runtime entry will fall back to surface/theme/default name".to_owned());
    }
    Ok(warnings)
}

pub fn entry_names(xmlcentral: &str) -> Vec<String> {
    let mut out = attr_values(xmlcentral, "Entry", "name");
    if out.is_empty() {
        out.extend(attr_values(xmlcentral, "Surface", "name"));
    }
    if out.is_empty() {
        out.extend(attr_values(xmlcentral, "Theme", "name"));
    }
    if out.is_empty() {
        out.push("surface".to_owned());
    }
    out.sort();
    out.dedup();
    out
}

pub fn dependencies(xmlcentral: &str) -> Vec<String> {
    let mut out = Vec::new();
    out.extend(attr_values(xmlcentral, "ThemeRef", "ref"));
    out.extend(attr_values(xmlcentral, "ComponentRef", "ref"));
    out.extend(attr_values(xmlcentral, "Import", "ref"));
    out.extend(attr_values(xmlcentral, "Surface", "theme"));
    out.retain(|value| !value.trim().is_empty());
    out.sort();
    out.dedup();
    out
}

pub fn normalize_logical_path(value: &str) -> String {
    let clean = value.trim().replace('\\', "/").trim_start_matches("./").trim_start_matches('/').to_owned();
    if clean.starts_with("assets/") || clean.is_empty() { clean } else { format!("assets/{clean}") }
}

fn parse_header(bytes: &[u8]) -> Result<NeuiHeader, String> {
    if bytes.len() < HEADER_LEN {
        return Err(format!("NEF8 header too small: bytes={} expected>={}", bytes.len(), HEADER_LEN));
    }
    if bytes.get(0..4) != Some(b"NEF8") {
        return Err("NEF8 magic mismatch".to_owned());
    }
    Ok(NeuiHeader {
        version: read_u16(bytes, 4)?,
        header_len: read_u16(bytes, 6)?,
        content_kind: read_u16(bytes, 8)?,
        flags: read_u16(bytes, 10)?,
        compression: read_u16(bytes, 12)?,
        body_offset: read_u64(bytes, 16)?,
        body_len: read_u64(bytes, 24)?,
        body_uncompressed_len: read_u64(bytes, 32)?,
        entry_count: read_u64(bytes, 40)?,
        body_raw_hash: read_hash32(bytes, 64)?,
        stable_file_id: read_u64(bytes, 96)?,
    })
}

#[derive(Debug, Clone)]
struct NeuiHeader {
    version: u16,
    header_len: u16,
    content_kind: u16,
    flags: u16,
    compression: u16,
    body_offset: u64,
    body_len: u64,
    body_uncompressed_len: u64,
    entry_count: u64,
    body_raw_hash: [u8; 32],
    stable_file_id: u64,
}

fn deflate(bytes: &[u8]) -> Result<Vec<u8>, String> {
    let mut encoder = DeflateEncoder::new(Vec::new(), Compression::default());
    encoder.write_all(bytes).map_err(|e| e.to_string())?;
    encoder.finish().map_err(|e| e.to_string())
}

fn inflate(bytes: &[u8]) -> Result<Vec<u8>, String> {
    let mut decoder = DeflateDecoder::new(bytes);
    let mut out = Vec::new();
    decoder.read_to_end(&mut out).map_err(|e| format!("deflate decode failed: {e}"))?;
    Ok(out)
}

fn root_name(xml: &str) -> Option<String> {
    let mut rest = xml.trim_start();
    if rest.starts_with("<?") {
        let end = rest.find("?>")?;
        rest = rest.get(end + 2..)?.trim_start();
    }
    let open = rest.strip_prefix('<')?;
    let name_end = open.find(|c: char| c.is_ascii_whitespace() || c == '>' || c == '/')?;
    Some(open.get(..name_end)?.to_owned())
}

fn count_open_tags(xml: &str, name: &str) -> usize {
    let needle = format!("<{name}");
    let mut count = 0usize;
    let mut search = 0usize;
    while let Some(pos_rel) = xml[search..].find(&needle) {
        let pos = search + pos_rel;
        let next = xml.as_bytes().get(pos + needle.len()).copied();
        if matches!(next, Some(b' ') | Some(b'\t') | Some(b'\n') | Some(b'\r') | Some(b'>') | Some(b'/')) {
            count += 1;
        }
        search = pos + needle.len();
    }
    count
}

fn first_attr_value(xml: &str, tag: &str, attr: &str) -> Option<String> {
    attr_values(xml, tag, attr).into_iter().next()
}

fn attr_values(xml: &str, tag: &str, attr: &str) -> Vec<String> {
    let needle = format!("<{tag}");
    let mut out = Vec::new();
    let mut search = 0usize;
    while let Some(pos_rel) = xml[search..].find(&needle) {
        let pos = search + pos_rel;
        let Some(open_end_rel) = xml[pos..].find('>') else { break; };
        let open_end = pos + open_end_rel;
        let open = &xml[pos..=open_end];
        if let Some(value) = attr_value(open, attr) {
            out.push(value);
        }
        search = open_end + 1;
    }
    out
}

fn attr_value(open: &str, key: &str) -> Option<String> {
    let bytes = open.as_bytes();
    let mut i = 0usize;
    while i < bytes.len() {
        while i < bytes.len() && !(bytes[i].is_ascii_alphabetic() || bytes[i] == b'_') { i += 1; }
        let key_start = i;
        while i < bytes.len() && (bytes[i].is_ascii_alphanumeric() || bytes[i] == b'_' || bytes[i] == b'-' || bytes[i] == b'.' || bytes[i] == b':') { i += 1; }
        let found = open.get(key_start..i)?.trim();
        while i < bytes.len() && bytes[i].is_ascii_whitespace() { i += 1; }
        if i >= bytes.len() || bytes[i] != b'=' { continue; }
        i += 1;
        while i < bytes.len() && bytes[i].is_ascii_whitespace() { i += 1; }
        if i >= bytes.len() || (bytes[i] != b'"' && bytes[i] != b'\'') { continue; }
        let quote = bytes[i];
        i += 1;
        let value_start = i;
        while i < bytes.len() && bytes[i] != quote { i += 1; }
        let value = open.get(value_start..i)?.to_owned();
        if found == key {
            return Some(xml_unescape(&value));
        }
        i = i.saturating_add(1);
    }
    None
}

fn xml_unescape(value: &str) -> String {
    value
        .replace("&quot;", "\"")
        .replace("&apos;", "'")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&amp;", "&")
}

fn stable_u64(value: &str) -> u64 {
    let h = blake3::hash(value.as_bytes());
    u64::from_le_bytes(h.as_bytes()[0..8].try_into().expect("hash slice"))
}

fn write_u16(out: &mut [u8], offset: usize, value: u16) { out[offset..offset + 2].copy_from_slice(&value.to_le_bytes()); }
fn write_u64(out: &mut [u8], offset: usize, value: u64) { out[offset..offset + 8].copy_from_slice(&value.to_le_bytes()); }
fn read_u16(bytes: &[u8], offset: usize) -> Result<u16, String> {
    let slice = bytes.get(offset..offset + 2).ok_or_else(|| format!("NEF8 header truncated at u16 offset {offset}"))?;
    Ok(u16::from_le_bytes([slice[0], slice[1]]))
}
fn read_u64(bytes: &[u8], offset: usize) -> Result<u64, String> {
    let slice = bytes.get(offset..offset + 8).ok_or_else(|| format!("NEF8 header truncated at u64 offset {offset}"))?;
    Ok(u64::from_le_bytes([slice[0], slice[1], slice[2], slice[3], slice[4], slice[5], slice[6], slice[7]]))
}
fn read_hash32(bytes: &[u8], offset: usize) -> Result<[u8; 32], String> {
    let slice = bytes.get(offset..offset + 32).ok_or_else(|| format!("NEF8 header truncated at hash32 offset {offset}"))?;
    let mut out = [0u8; 32];
    out.copy_from_slice(slice);
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn sample_xml() -> &'static str {
        r#"<?xml version="1.0" encoding="utf-8" standalone="yes"?>
<NeUiDictionary schema="newengine.neui.xmlcentral.v1">
  <Entries><Entry name="surface" kind="ui_surface" /></Entries>
  <Surface name="engine.ui.test" root="layout.main" theme="assets/ui/themes/northstar_editor.neui@editor_light" />
  <Layout name="layout.main"><Panel id="root"><Button id="ok" text="OK" action="ui.ok" /></Panel></Layout>
</NeUiDictionary>"#
    }

    #[test]
    fn neui_rejects_bad_magic() {
        let err = inspect_nef8_json(b"BAD!").unwrap_err();
        assert!(err.contains("header too small") || err.contains("magic"));
    }

    #[test]
    fn neui_rejects_wrong_content_kind() {
        let mut bytes = pack_xmlcentral_to_nef8(sample_xml(), "assets/ui/test.neui", "test", 1).unwrap();
        bytes[8] = 7;
        let err = decode_nef8_xmlcentral(&bytes).unwrap_err();
        assert!(err.contains("not ui_dictionary"));
    }

    #[test]
    fn neui_compile_then_inspect_roundtrip() {
        let bytes = pack_xmlcentral_to_nef8(sample_xml(), "assets/ui/test.neui", "test", 1).unwrap();
        let xml = decode_nef8_xmlcentral(&bytes).unwrap();
        assert!(xml.contains("<NeUiDictionary"));
        let inspect = inspect_nef8_json(&bytes).unwrap();
        assert_eq!(inspect["ok"], true);
        assert_eq!(inspect["xmlcentral"]["surface_count"], 1);
    }

    #[test]
    fn neui_manifest_contains_file_entry_refs() {
        let manifest = manifest_json_for_xmlcentral(sample_xml(), "assets/ui/test.neui").unwrap();
        assert_eq!(manifest["entries"][0]["entry_ref"], "assets/ui/test.neui@surface");
        assert_eq!(manifest["semantic_gateway"], "engine.assets.ui");
    }
}
