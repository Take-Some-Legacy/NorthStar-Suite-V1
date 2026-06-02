use newengine_model_domain_api::{
    DefinitionBounds, DefinitionDictionaries, DefinitionEntriesManifest, DefinitionEntry,
    DEFINITION_ENTRIES_SCHEMA,
};
use quick_xml::events::{BytesStart, Event};
use quick_xml::Reader;

use crate::ytyp::DecodedYtypSource;
use crate::ytyp_manifest::{
    canonicalize_entry, normalize_asset_key_str, normalize_manifest, selector_matches, selector_string,
};

pub(crate) fn parse_ytyp_xml_manifest(
    logical_path: &str,
    decoded: DecodedYtypSource,
    selector: &serde_json::Value,
) -> Result<DefinitionEntriesManifest, String> {
    let text = std::str::from_utf8(&decoded.payload)
        .map_err(|e| format!("ytyp XML payload is not utf-8 path='{logical_path}' err='{e}'"))?;
    if !text.contains("<CMapTypes") {
        return Err(format!("ytyp XML payload missing <CMapTypes> root path='{logical_path}'"));
    }

    let selector_name = selector_string(selector, "name")
        .or_else(|| selector_string(selector, "asset_name"))
        .or_else(|| selector_string(selector, "selector"));

    let mut reader = Reader::from_reader(decoded.payload.as_slice());
    reader.config_mut().trim_text(true);

    let mut buf = Vec::new();
    let mut manifest = DefinitionEntriesManifest {
        schema: DEFINITION_ENTRIES_SCHEMA.to_owned(),
        codec: "asset.codec.listfile.ytyp".to_owned(),
        source_format: decoded.source_format.clone(),
        source_encoding: decoded.source_encoding.clone(),
        source: normalize_asset_key_str(logical_path),
        name: String::new(),
        definition_entries: Vec::new(),
    };
    let mut stack: Vec<String> = Vec::new();
    let mut current: Option<DefinitionEntry> = None;
    let mut text_field: Option<String> = None;

    loop {
        match reader.read_event_into(&mut buf) {
            Ok(Event::Start(e)) => {
                let tag = element_name(&e);
                stack.push(tag.clone());
                if tag == "Item" && stack.iter().any(|s| s == "archetypes") {
                    let entry = DefinitionEntry {
                        entry_kind: attr_value(&e, b"type").unwrap_or_else(|| "CBaseArchetypeDef".to_owned()),
                        bounds: DefinitionBounds::default(),
                        dictionaries: DefinitionDictionaries::default(),
                        ..DefinitionEntry::default()
                    };
                    current = Some(entry);
                } else {
                    apply_empty_like_tag(&mut current, &tag, &e);
                    if is_text_field(&tag) {
                        text_field = Some(tag);
                    }
                }
            }
            Ok(Event::Empty(e)) => {
                let tag = element_name(&e);
                apply_empty_like_tag(&mut current, &tag, &e);
                if let Some(entry) = current.as_mut() {
                    apply_text_field(entry, &tag, "");
                }
            }
            Ok(Event::Text(e)) => {
                let value = String::from_utf8_lossy(e.as_ref()).trim().to_owned();
                if value.is_empty() {
                    buf.clear();
                    continue;
                }
                if let Some(field) = text_field.as_deref() {
                    if let Some(entry) = current.as_mut() {
                        apply_text_field(entry, field, &value);
                    } else if field == "name" && stack.last().map(|s| s.as_str()) == Some("name") {
                        manifest.name = value;
                    }
                }
            }
            Ok(Event::End(e)) => {
                let tag = String::from_utf8_lossy(e.name().as_ref()).to_string();
                if tag == "Item" {
                    if let Some(mut entry) = current.take() {
                        canonicalize_entry(&mut entry);
                        if selector_matches(selector_name.as_deref(), &entry) {
                            manifest.definition_entries.push(entry);
                        }
                    }
                }
                if text_field.as_deref() == Some(tag.as_str()) {
                    text_field = None;
                }
                let _ = stack.pop();
            }
            Ok(Event::Eof) => break,
            Err(e) => return Err(format!("ytyp xml parse failed path='{logical_path}' err='{e}'")),
            _ => {}
        }
        buf.clear();
    }

    normalize_manifest(logical_path, &decoded, &mut manifest);
    Ok(manifest)
}

fn is_text_field(tag: &str) -> bool {
    matches!(
        tag,
        "name"
            | "textureDictionary"
            | "clipDictionary"
            | "drawableDictionary"
            | "physicsDictionary"
            | "assetType"
            | "assetName"
    )
}

fn apply_empty_like_tag(current: &mut Option<DefinitionEntry>, tag: &str, e: &BytesStart<'_>) {
    let Some(entry) = current.as_mut() else { return; };
    match tag {
        "lodDist" => entry.lod_dist = attr_f32(e, b"value"),
        "flags" => entry.flags = attr_u32(e, b"value"),
        "specialAttribute" => entry.special_attribute = attr_u32(e, b"value"),
        "bbMin" => entry.bounds.bb_min = attr_vec3(e),
        "bbMax" => entry.bounds.bb_max = attr_vec3(e),
        "bsCentre" => entry.bounds.bs_centre = attr_vec3(e),
        "bsRadius" => entry.bounds.bs_radius = attr_f32(e, b"value"),
        "hdTextureDist" => entry.hd_texture_dist = attr_f32(e, b"value"),
        _ => {}
    }
}

fn apply_text_field(entry: &mut DefinitionEntry, field: &str, value: &str) {
    let value = value.trim();
    match field {
        "name" => entry.name = value.to_owned(),
        "textureDictionary" => entry.dictionaries.texture = non_empty(value),
        "clipDictionary" => entry.dictionaries.clip = non_empty(value),
        "drawableDictionary" => entry.dictionaries.drawable = non_empty(value),
        "physicsDictionary" => entry.dictionaries.physics = non_empty(value),
        "assetType" => entry.asset_type = value.to_owned(),
        "assetName" => entry.asset_name = value.to_owned(),
        _ => {}
    }
}

fn element_name(e: &BytesStart<'_>) -> String {
    String::from_utf8_lossy(e.name().as_ref()).to_string()
}

fn attr_vec3(e: &BytesStart<'_>) -> [f32; 3] {
    [attr_f32(e, b"x"), attr_f32(e, b"y"), attr_f32(e, b"z")]
}

fn attr_f32(e: &BytesStart<'_>, key: &[u8]) -> f32 {
    attr_value(e, key)
        .and_then(|v| v.parse::<f32>().ok())
        .unwrap_or(0.0)
}

fn attr_u32(e: &BytesStart<'_>, key: &[u8]) -> u32 {
    attr_value(e, key)
        .and_then(|v| v.parse::<u32>().ok())
        .unwrap_or(0)
}

fn attr_value(e: &BytesStart<'_>, key: &[u8]) -> Option<String> {
    for attr in e.attributes().with_checks(false).flatten() {
        if attr.key.as_ref() == key {
            return Some(String::from_utf8_lossy(attr.value.as_ref()).to_string());
        }
    }
    None
}

fn non_empty(value: &str) -> Option<String> {
    let trimmed = value.trim();
    if trimmed.is_empty() { None } else { Some(trimmed.to_owned()) }
}
