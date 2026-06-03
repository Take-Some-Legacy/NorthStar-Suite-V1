use std::collections::HashSet;

use std::io::{Read, Write};



use flate2::{read::DeflateDecoder, write::DeflateEncoder, Compression};

use serde_json::json;



use crate::drawable::{stable_hash64, DrawableDictionary, DrawableModel, Vertex, CONTENT_KIND_YDD_DRAWABLE_DICTIONARY};



pub const HEADER_LEN: usize = 128;

const FLAG_BODY_DEFLATE: u16 = 0x0001;

const COMPRESSION_DEFLATE: u16 = 1;

const BODY_SCHEMA_VERSION: u32 = 1;

const BODY_HEADER_LEN: usize = 40;

const ENTRY_RECORD_LEN: usize = 80;



#[derive(Debug, Clone)]

pub struct Nef8Header {

    pub version: u16,

    pub header_len: u16,

    pub content_kind: u16,

    pub flags: u16,

    pub compression: u16,

    pub body_offset: u64,

    pub body_len: u64,

    pub body_uncompressed_len: u64,

    pub entry_count: u64,

    pub stable_file_id: u64,

    body_hash: [u8; 32],

}



#[derive(Debug, Clone)]

pub struct ResidentEntryInfo {

    pub name: String,

    pub selector: String,

    pub mesh_count: u32,

    pub vertex_count: u32,

    pub index_count: u32,

    pub material_count: u32,

    pub payload_len: u64,

}



#[derive(Debug, Clone)]

pub struct ParsedDrawableDictionary {

    pub header: Nef8Header,

    pub entries: Vec<ResidentEntryInfo>,

}



pub fn pack_ydd(dict: &DrawableDictionary, logical_path: &str) -> Result<Vec<u8>, String> {

    validate_dictionary(dict)?;

    let body = encode_body(dict)?;

    let compressed = deflate(&body)?;

    let body_hash = blake3::hash(&body);

    let logical = normalize_logical_path(logical_path);



    let mut out = vec![0u8; HEADER_LEN];

    out[0..4].copy_from_slice(b"NEF8");

    write_u16(&mut out, 4, 1);

    write_u16(&mut out, 6, HEADER_LEN as u16);

    write_u16(&mut out, 8, CONTENT_KIND_YDD_DRAWABLE_DICTIONARY);

    write_u16(&mut out, 10, FLAG_BODY_DEFLATE);

    write_u16(&mut out, 12, COMPRESSION_DEFLATE);

    write_u64(&mut out, 16, HEADER_LEN as u64);

    write_u64(&mut out, 24, compressed.len() as u64);

    write_u64(&mut out, 32, body.len() as u64);

    write_u64(&mut out, 40, dict.models.len() as u64);

    write_u64(&mut out, 48, 0);

    write_u64(&mut out, 56, 0);

    out[64..96].copy_from_slice(body_hash.as_bytes());

    write_u64(&mut out, 96, stable_hash64(&logical));

    write_u64(&mut out, 104, stable_hash64("northstar.ydd.drawable_dictionary.v1"));

    write_u64(&mut out, 112, BODY_SCHEMA_VERSION as u64);

    out.extend_from_slice(&compressed);

    Ok(out)

}



pub fn parse_ydd(bytes: &[u8], file_name: &str) -> Result<ParsedDrawableDictionary, String> {

    let header = parse_header(bytes)?;

    if header.content_kind != CONTENT_KIND_YDD_DRAWABLE_DICTIONARY {

        return Err(format!("NEF8 content_kind={} is not ydd drawable_dictionary ({})", header.content_kind, CONTENT_KIND_YDD_DRAWABLE_DICTIONARY));

    }

    let body = decode_body(bytes, &header)?;

    let entries = parse_body_index(&body, file_name)?;

    Ok(ParsedDrawableDictionary { header, entries })

}



pub fn inspect_json(bytes: &[u8], file_name: &str) -> Result<serde_json::Value, String> {

    let parsed = parse_ydd(bytes, file_name)?;

    let entries = parsed.entries.iter().map(|e| json!({

        "name": e.name,

        "selector": e.selector,

        "mesh_count": e.mesh_count,

        "vertex_count": e.vertex_count,

        "index_count": e.index_count,

        "material_count": e.material_count,

        "payload_len": e.payload_len,

    })).collect::<Vec<_>>();

    Ok(json!({

        "schema": "northstar.ydd.inspect.v1",

        "ok": true,

        "container": "NEF8 ListFile",

        "content_kind": "drawable_dictionary",

        "resident": true,

        "file": normalize_logical_path(file_name),

        "header": {

            "magic": "NEF8",

            "version": parsed.header.version,

            "header_len": parsed.header.header_len,

            "content_kind": parsed.header.content_kind,

            "compression": parsed.header.compression,

            "entry_count": parsed.header.entry_count,

            "body_offset": parsed.header.body_offset,

            "body_len": parsed.header.body_len,

            "body_uncompressed_len": parsed.header.body_uncompressed_len,

            "stable_file_id": format!("{:016x}", parsed.header.stable_file_id),

        },

        "drawable_dictionary": { "model_count": parsed.entries.len(), "entries": entries }

    }))

}



pub fn decode_body(bytes: &[u8], header: &Nef8Header) -> Result<Vec<u8>, String> {

    if header.version != 1 { return Err(format!("unsupported NEF8 version {}", header.version)); }

    if header.header_len as usize != HEADER_LEN { return Err(format!("unsupported NEF8 header_len {}", header.header_len)); }

    if header.compression != COMPRESSION_DEFLATE || (header.flags & FLAG_BODY_DEFLATE) == 0 {

        return Err(format!("YDD NEF8 body must be deflate flags=0x{:04x} compression={}", header.flags, header.compression));

    }

    let start = header.body_offset as usize;

    let end = start.checked_add(header.body_len as usize).ok_or("NEF8 body range overflow")?;

    let compressed = bytes.get(start..end).ok_or_else(|| format!("NEF8 body range outside file offset={} len={} file={}", header.body_offset, header.body_len, bytes.len()))?;

    let inflated = inflate(compressed)?;

    if inflated.len() as u64 != header.body_uncompressed_len {

        return Err(format!("NEF8 inflated body size mismatch actual={} expected={}", inflated.len(), header.body_uncompressed_len));

    }

    if blake3::hash(&inflated).as_bytes() != &header.body_hash { return Err("NEF8 body hash mismatch after inflate".to_owned()); }

    Ok(inflated)

}



pub fn parse_header(bytes: &[u8]) -> Result<Nef8Header, String> {

    if bytes.len() < HEADER_LEN { return Err(format!("NEF8 header too small: bytes={} expected>={}", bytes.len(), HEADER_LEN)); }

    if bytes.get(0..4) != Some(b"NEF8") { return Err("NEF8 magic mismatch".to_owned()); }

    Ok(Nef8Header {

        version: read_u16(bytes, 4)?,

        header_len: read_u16(bytes, 6)?,

        content_kind: read_u16(bytes, 8)?,

        flags: read_u16(bytes, 10)?,

        compression: read_u16(bytes, 12)?,

        body_offset: read_u64(bytes, 16)?,

        body_len: read_u64(bytes, 24)?,

        body_uncompressed_len: read_u64(bytes, 32)?,

        entry_count: read_u64(bytes, 40)?,

        body_hash: read_hash32(bytes, 64)?,

        stable_file_id: read_u64(bytes, 96)?,

    })

}



pub fn validate_dictionary(dict: &DrawableDictionary) -> Result<(), String> {

    if dict.models.is_empty() { return Err("YDD drawable dictionary must contain at least one resident model".to_owned()); }

    let mut names = HashSet::new();

    let mut hashes = HashSet::new();

    for model in &dict.models {

        if model.name.trim().is_empty() { return Err("YDD model entry has empty name".to_owned()); }

        let lower = model.name.to_ascii_lowercase();

        if !names.insert(lower.clone()) { return Err(format!("duplicate YDD model name '{}'", model.name)); }

        let hash = stable_hash64(&lower);

        if !hashes.insert(hash) { return Err(format!("duplicate YDD model hash for '{}'", model.name)); }

        if model.meshes.is_empty() { return Err(format!("YDD model '{}' has no meshes", model.name)); }

        for mesh in &model.meshes {

            if mesh.vertices.is_empty() { return Err(format!("YDD model '{}' mesh '{}' has no vertices", model.name, mesh.name)); }

            if mesh.indices.len() % 3 != 0 { return Err(format!("YDD model '{}' mesh '{}' index_count is not triangulated", model.name, mesh.name)); }

            if let Some(material) = &mesh.material_ref { crate::drawable::validate_material_ref(material)?; }

            for v in &mesh.vertices {

                for f in v.position.iter().chain(v.normal.iter()).chain(v.uv0.iter()) {

                    if !f.is_finite() { return Err(format!("YDD model '{}' contains NaN/Inf vertex data", model.name)); }

                }

            }

        }

    }

    Ok(())

}



fn encode_body(dict: &DrawableDictionary) -> Result<Vec<u8>, String> {

    let entry_count = dict.models.len();

    let entry_table_offset = BODY_HEADER_LEN;

    let string_table_offset = entry_table_offset + entry_count * ENTRY_RECORD_LEN;

    let mut strings = Vec::<u8>::new();

    let mut payloads = Vec::<Vec<u8>>::new();

    let mut records = Vec::<EntryBuildRecord>::new();



    for model in &dict.models {

        let name_offset = push_string(&mut strings, &model.name);

        let source_offset = push_string(&mut strings, &model.source_path);

        let mut payload = Vec::new();

        write_model_payload(&mut payload, model, &mut strings)?;

        records.push(EntryBuildRecord {

            name: model.name.clone(), name_offset, source_offset,

            mesh_count: model.meshes.len() as u32,

            vertex_count: model.meshes.iter().map(|m| m.vertices.len() as u32).sum(),

            index_count: model.meshes.iter().map(|m| m.indices.len() as u32).sum(),

            material_count: model.meshes.iter().filter(|m| m.material_ref.is_some()).count() as u32,

            bounds_min: model.bounds.min, bounds_max: model.bounds.max,

            payload_len: payload.len() as u64,

        });

        payloads.push(payload);

    }



    let payload_offset = string_table_offset + strings.len();

    let payload_len: usize = payloads.iter().map(|p| p.len()).sum();

    let mut out = Vec::with_capacity(payload_offset + payload_len);

    write_u32_vec(&mut out, BODY_SCHEMA_VERSION);

    write_u32_vec(&mut out, entry_count as u32);

    write_u64_vec(&mut out, entry_table_offset as u64);

    write_u64_vec(&mut out, string_table_offset as u64);

    write_u64_vec(&mut out, strings.len() as u64);

    write_u64_vec(&mut out, payload_offset as u64);



    let mut running_payload_offset = payload_offset as u64;

    for record in &records {

        write_u64_vec(&mut out, stable_hash64(&record.name));

        write_u32_vec(&mut out, record.name_offset);

        write_u32_vec(&mut out, record.source_offset);

        write_u32_vec(&mut out, record.mesh_count);

        write_u32_vec(&mut out, record.vertex_count);

        write_u32_vec(&mut out, record.index_count);

        write_u32_vec(&mut out, record.material_count);

        write_u32_vec(&mut out, 0);

        write_f32_array(&mut out, record.bounds_min);

        write_f32_array(&mut out, record.bounds_max);

        write_u32_vec(&mut out, 0);

        // ENTRY_RECORD_LEN is 80. The parser expects payload_offset at +64 and payload_len at +72.

        // Keep exactly one reserved u32 after bounds; a second one shifts payload fields and corrupts self-parse.

        write_u64_vec(&mut out, running_payload_offset);

        write_u64_vec(&mut out, record.payload_len);

        running_payload_offset += record.payload_len;

    }

    debug_assert_eq!(out.len(), string_table_offset);

    out.extend_from_slice(&strings);

    for payload in payloads { out.extend_from_slice(&payload); }

    Ok(out)

}



fn parse_body_index(body: &[u8], file_name: &str) -> Result<Vec<ResidentEntryInfo>, String> {

    if body.len() < BODY_HEADER_LEN { return Err(format!("YDD body too small: {}", body.len())); }

    let version = read_u32(body, 0)?;

    if version != BODY_SCHEMA_VERSION { return Err(format!("unsupported YDD body schema version {version}")); }

    let entry_count = read_u32(body, 4)? as usize;

    let table_offset = read_u64(body, 8)? as usize;

    let string_offset = read_u64(body, 16)? as usize;

    let string_len = read_u64(body, 24)? as usize;

    let payload_offset = read_u64(body, 32)? as usize;

    if table_offset.checked_add(entry_count * ENTRY_RECORD_LEN).ok_or("YDD entry table range overflow")? > body.len() { return Err("YDD entry table outside body".to_owned()); }

    if string_offset.checked_add(string_len).ok_or("YDD string table range overflow")? > body.len() { return Err("YDD string table outside body".to_owned()); }

    if payload_offset > body.len() { return Err("YDD payload offset outside body".to_owned()); }

    let strings = &body[string_offset..string_offset + string_len];

    let mut entries = Vec::with_capacity(entry_count);

    for i in 0..entry_count {

        let o = table_offset + i * ENTRY_RECORD_LEN;

        let name_offset = read_u32(body, o + 8)?;

        let name = read_string(strings, name_offset)?;

        let payload_start = read_u64(body, o + 64)? as usize;

        let payload_len = read_u64(body, o + 72)? as usize;

        if payload_start < payload_offset {

            return Err(format!("YDD entry '{}' payload starts before payload table", name));

        }

        if payload_start.checked_add(payload_len).ok_or("YDD entry payload range overflow")? > body.len() { return Err(format!("YDD entry '{}' payload outside body", name)); }

        entries.push(ResidentEntryInfo {

            selector: format!("{}@{}", normalize_logical_path(file_name), name),

            name,

            mesh_count: read_u32(body, o + 16)?,

            vertex_count: read_u32(body, o + 20)?,

            index_count: read_u32(body, o + 24)?,

            material_count: read_u32(body, o + 28)?,

            payload_len: payload_len as u64,

        });

    }

    Ok(entries)

}



fn write_model_payload(out: &mut Vec<u8>, model: &DrawableModel, strings: &mut Vec<u8>) -> Result<(), String> {

    write_u32_vec(out, model.meshes.len() as u32);

    write_u32_vec(out, 0);

    for mesh in &model.meshes {

        let name_offset = push_string(strings, &mesh.name);

        let material_offset = mesh.material_ref.as_ref().map(|m| push_string(strings, m)).unwrap_or(u32::MAX);

        write_u32_vec(out, name_offset);

        write_u32_vec(out, material_offset);

        write_u32_vec(out, mesh.vertices.len() as u32);

        write_u32_vec(out, mesh.indices.len() as u32);

        write_f32_array(out, mesh.bounds.min);

        write_f32_array(out, mesh.bounds.max);

        for vertex in &mesh.vertices { write_vertex(out, *vertex); }

        for idx in &mesh.indices { write_u32_vec(out, *idx); }

    }

    Ok(())

}



struct EntryBuildRecord { name: String, name_offset: u32, source_offset: u32, mesh_count: u32, vertex_count: u32, index_count: u32, material_count: u32, bounds_min: [f32; 3], bounds_max: [f32; 3], payload_len: u64 }

fn write_vertex(out: &mut Vec<u8>, v: Vertex) { write_f32_array(out, v.position); write_f32_array(out, v.normal); write_f32_array2(out, v.uv0); }

fn write_f32_array(out: &mut Vec<u8>, values: [f32; 3]) { for value in values { out.extend_from_slice(&value.to_le_bytes()); } }

fn write_f32_array2(out: &mut Vec<u8>, values: [f32; 2]) { for value in values { out.extend_from_slice(&value.to_le_bytes()); } }

fn push_string(strings: &mut Vec<u8>, value: &str) -> u32 { let offset = strings.len() as u32; strings.extend_from_slice(value.as_bytes()); strings.push(0); offset }

fn read_string(strings: &[u8], offset: u32) -> Result<String, String> { let start = offset as usize; if start >= strings.len() { return Err(format!("YDD string offset {offset} outside table")); } let len = strings[start..].iter().position(|b| *b == 0).ok_or("YDD string is not nul-terminated")?; String::from_utf8(strings[start..start + len].to_vec()).map_err(|e| format!("YDD string is not UTF-8: {e}")) }

fn deflate(bytes: &[u8]) -> Result<Vec<u8>, String> { let mut encoder = DeflateEncoder::new(Vec::new(), Compression::default()); encoder.write_all(bytes).map_err(|e| e.to_string())?; encoder.finish().map_err(|e| e.to_string()) }

fn inflate(bytes: &[u8]) -> Result<Vec<u8>, String> { let mut decoder = DeflateDecoder::new(bytes); let mut out = Vec::new(); decoder.read_to_end(&mut out).map_err(|e| format!("deflate decode failed: {e}"))?; Ok(out) }

pub fn normalize_logical_path(value: &str) -> String { value.replace('\\', "/").trim_start_matches("./").to_ascii_lowercase() }

fn write_u16(out: &mut [u8], offset: usize, value: u16) { out[offset..offset + 2].copy_from_slice(&value.to_le_bytes()); }

fn write_u64(out: &mut [u8], offset: usize, value: u64) { out[offset..offset + 8].copy_from_slice(&value.to_le_bytes()); }

fn write_u32_vec(out: &mut Vec<u8>, value: u32) { out.extend_from_slice(&value.to_le_bytes()); }

fn write_u64_vec(out: &mut Vec<u8>, value: u64) { out.extend_from_slice(&value.to_le_bytes()); }

fn read_u16(bytes: &[u8], offset: usize) -> Result<u16, String> { let s = bytes.get(offset..offset + 2).ok_or_else(|| format!("truncated u16 at {offset}"))?; Ok(u16::from_le_bytes([s[0], s[1]])) }

fn read_u32(bytes: &[u8], offset: usize) -> Result<u32, String> { let s = bytes.get(offset..offset + 4).ok_or_else(|| format!("truncated u32 at {offset}"))?; Ok(u32::from_le_bytes([s[0], s[1], s[2], s[3]])) }

fn read_u64(bytes: &[u8], offset: usize) -> Result<u64, String> { let s = bytes.get(offset..offset + 8).ok_or_else(|| format!("truncated u64 at {offset}"))?; Ok(u64::from_le_bytes([s[0], s[1], s[2], s[3], s[4], s[5], s[6], s[7]])) }

fn read_hash32(bytes: &[u8], offset: usize) -> Result<[u8; 32], String> { let s = bytes.get(offset..offset + 32).ok_or_else(|| format!("truncated hash32 at {offset}"))?; let mut out = [0u8; 32]; out.copy_from_slice(s); Ok(out) }

