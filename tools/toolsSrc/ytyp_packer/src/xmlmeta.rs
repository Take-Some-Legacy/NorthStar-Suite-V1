use serde_json::{json, Value};

pub fn validate_metadata_xml(xml: &str, source_ref: &str) -> Result<Vec<String>, String> {
    let root = root_name(xml).ok_or_else(|| format!("{source_ref}: XML document has no root element"))?;
    if root.trim().is_empty() {
        return Err(format!("{source_ref}: XML root element name is empty"));
    }
    let mut warnings = Vec::new();
    if root == "CMapTypes" {
        warnings.push("CMapTypes is accepted as one metadata profile, but .ytyp is no longer world/archetype-only".to_owned());
    }
    if entry_names(xml).is_empty() {
        warnings.push("no explicit <Entry>/<MetadataEntry>/<Meta>/<Object> name/id found; entry name will fall back to XML root".to_owned());
    }
    Ok(warnings)
}

pub fn manifest_json_for_metadata(xml: &str, logical_path: &str) -> Result<Value, String> {
    validate_metadata_xml(xml, logical_path)?;
    let source = normalize_logical_path(logical_path);
    Ok(json!({
        "schema": "asset.inspect.ytyp.v1",
        "source": source,
        "asset_kind": "generic_metadata_dictionary",
        "container": "newengine.listfile.nef8.ytyp",
        "semantic_gateway": "engine.assets.metadata",
        "runtime_policy": "generic XML metadata; consumers opt in through explicit refs/contracts",
        "entries": entry_names(xml).iter().map(|entry| json!({
            "name": entry,
            "entry_ref": format!("{}@{}", source, entry),
            "asset_kind": "generic_metadata_entry",
            "route": {
                "gateway": "engine.assets.metadata",
                "method": "assets.metadata.decode_xml_v1",
                "semantic_owner": "consumer-domain-explicit"
            }
        })).collect::<Vec<_>>(),
        "dependencies": dependencies(xml),
        "summary": summary_json(xml),
    }))
}

pub fn metadata_projection_json(xml: &str, logical_path: &str) -> Result<Value, String> {
    validate_metadata_xml(xml, logical_path)?;
    Ok(json!({
        "schema": "newengine.assets.metadata.projection.v1",
        "note": "diagnostic projection; authoritative interpretation belongs to the consumer domain that requested this metadata",
        "document_ref": normalize_logical_path(logical_path),
        "root": root_name(xml).unwrap_or_else(|| "<unknown>".to_owned()),
        "entries": entry_names(xml),
        "dependencies": dependencies(xml),
        "summary": summary_json(xml),
    }))
}

pub fn summary_json(xml: &str) -> Value {
    let entries = entry_names(xml);
    let deps = dependencies(xml);
    json!({
        "root": root_name(xml).unwrap_or_else(|| "<unknown>".to_owned()),
        "entries": entries,
        "entry_count": entries.len(),
        "dependencies": deps,
        "dependency_count": deps.len(),
        "metadata_node_count": count_any_open_tags(xml),
        "profile_hints": profile_hints(xml),
    })
}

pub fn entry_names(xml: &str) -> Vec<String> {
    let mut out = Vec::new();
    for tag in ["Entry", "MetadataEntry", "Meta", "Object", "Item", "Definition"] {
        out.extend(attr_values(xml, tag, "name"));
        out.extend(attr_values(xml, tag, "id"));
        out.extend(attr_values(xml, tag, "key"));
    }
    if out.is_empty() {
        out.extend(attr_values(xml, "archetype", "name"));
        out.extend(attr_values(xml, "Archetype", "name"));
    }
    out.retain(|value| !value.trim().is_empty());
    out.sort();
    out.dedup();
    if out.is_empty() {
        out.push(root_name(xml).unwrap_or_else(|| "metadata".to_owned()));
    }
    out
}

pub fn dependencies(xml: &str) -> Vec<String> {
    let mut out = Vec::new();
    for attr in [
        "ref", "asset", "asset_ref", "assetRef", "source", "target", "material", "model", "texture", "dictionary", "document", "metadata",
    ] {
        out.extend(all_attr_values(xml, attr));
    }
    out.retain(|value| looks_like_asset_ref(value));
    out.sort();
    out.dedup();
    out
}

pub fn normalize_logical_path(value: &str) -> String {
    let clean = value.trim().replace('\\', "/").trim_start_matches("./").trim_start_matches('/').to_owned();
    if clean.starts_with("assets/") || clean.is_empty() { clean } else { format!("assets/{clean}") }
}

fn profile_hints(xml: &str) -> Vec<String> {
    let mut out = Vec::new();
    if xml.contains("<CMapTypes") { out.push("profile.gta.cmaptypes".to_owned()); }
    if xml.contains("<Metadata") || xml.contains("<Meta") { out.push("profile.generic.metadata".to_owned()); }
    if xml.contains("material") || xml.contains("Material") { out.push("hint.material_refs".to_owned()); }
    if xml.contains("texture") || xml.contains("Texture") { out.push("hint.texture_refs".to_owned()); }
    out.sort();
    out.dedup();
    out
}

fn looks_like_asset_ref(value: &str) -> bool {
    let v = value.trim();
    if v.is_empty() { return false; }
    v.contains('@')
        || v.starts_with("assets/")
        || v.contains(".ytd")
        || v.contains(".ydd")
        || v.contains(".ytyp")
        || v.contains(".ymap")
        || v.contains(".nemat")
        || v.contains(".neui")
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

fn count_any_open_tags(xml: &str) -> usize {
    xml.as_bytes().windows(1).filter(|w| w[0] == b'<').count().saturating_sub(xml.matches("</").count())
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
        if let Some(value) = attr_value(open, attr) { out.push(value); }
        search = open_end + 1;
    }
    out
}

fn all_attr_values(xml: &str, attr: &str) -> Vec<String> {
    let mut out = Vec::new();
    let mut search = 0usize;
    while let Some(pos_rel) = xml[search..].find('<') {
        let pos = search + pos_rel;
        let Some(open_end_rel) = xml[pos..].find('>') else { break; };
        let open_end = pos + open_end_rel;
        let open = &xml[pos..=open_end];
        if !open.starts_with("</") {
            if let Some(value) = attr_value(open, attr) { out.push(value); }
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
        while i < bytes.len() && (bytes[i].is_ascii_alphanumeric() || matches!(bytes[i], b'_' | b'-' | b'.' | b':')) { i += 1; }
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
        if found == key { return Some(xml_unescape(&value)); }
        i = i.saturating_add(1);
    }
    None
}

fn xml_unescape(value: &str) -> String {
    value.replace("&quot;", "\"").replace("&apos;", "'").replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn generic_metadata_accepts_arbitrary_root() {
        let xml = r#"<AnyMetadata><Entry name="foo" asset="assets/a.ytd@bar" /></AnyMetadata>"#;
        assert!(validate_metadata_xml(xml, "x").is_ok());
        assert_eq!(entry_names(xml), vec!["foo"]);
        assert_eq!(dependencies(xml), vec!["assets/a.ytd@bar"]);
    }
}
