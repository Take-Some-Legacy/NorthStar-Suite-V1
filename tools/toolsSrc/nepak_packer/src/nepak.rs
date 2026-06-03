use std::fs;
use std::io::{Read, Write};
use std::path::Path;

use flate2::{read::DeflateDecoder, write::DeflateEncoder, Compression};
use serde_json::json;

use crate::fswalk::{safe_output_path, SourceFile};

const MAGIC: &[u8; 4] = b"NEPK";
const VERSION: u16 = 1;
const HEADER_LEN: usize = 96;
const ENTRY_LEN: usize = 96;
const FLAG_DEFLATE: u16 = 0x0001;

#[derive(Debug, Clone)]
pub struct PackageEntry {
    pub path: String,
    pub offset: u64,
    pub stored_len: u64,
    pub original_len: u64,
    pub flags: u16,
    pub hash: [u8; 32],
}

#[derive(Debug, Clone)]
pub struct ParsedPackage {
    pub entries: Vec<PackageEntry>,
}

pub fn pack_sources(sources: &[SourceFile], output: &Path, compress: bool) -> Result<(), String> {
    if sources.is_empty() { return Err("NEPAK pack requires at least one source file".to_owned()); }
    let mut strings = Vec::<u8>::new();
    let mut records = Vec::<BuildRecord>::new();
    let mut payloads = Vec::<Vec<u8>>::new();
    for source in sources {
        let bytes = fs::read(&source.disk_path).map_err(|e| format!("read '{}' failed: {e}", source.disk_path.display()))?;
        let stored = if compress { deflate(&bytes)? } else { bytes.clone() };
        let flags = if compress { FLAG_DEFLATE } else { 0 };
        let path_offset = push_string(&mut strings, &source.package_path);
        records.push(BuildRecord {
            path: source.package_path.clone(), path_offset,
            stored_len: stored.len() as u64,
            original_len: bytes.len() as u64,
            flags,
            hash: *blake3::hash(&bytes).as_bytes(),
        });
        payloads.push(stored);
    }

    let table_offset = HEADER_LEN as u64;
    let string_offset = table_offset + (records.len() * ENTRY_LEN) as u64;
    let payload_offset = string_offset + strings.len() as u64;
    let mut out = vec![0u8; HEADER_LEN];
    out[0..4].copy_from_slice(MAGIC);
    write_u16(&mut out, 4, VERSION);
    write_u16(&mut out, 6, HEADER_LEN as u16);
    write_u32(&mut out, 8, records.len() as u32);
    write_u64(&mut out, 16, table_offset);
    write_u64(&mut out, 24, string_offset);
    write_u64(&mut out, 32, strings.len() as u64);
    write_u64(&mut out, 40, payload_offset);
    write_u64(&mut out, 48, stable_id_for_entries(&records));

    let mut running = payload_offset;
    for record in &records {
        write_u64_vec(&mut out, stable_path_hash(&record.path));
        write_u32_vec(&mut out, record.path_offset);
        write_u16_vec(&mut out, record.flags);
        write_u16_vec(&mut out, 0);
        write_u64_vec(&mut out, running);
        write_u64_vec(&mut out, record.stored_len);
        write_u64_vec(&mut out, record.original_len);
        out.extend_from_slice(&record.hash);
        write_u64_vec(&mut out, 0);
        write_u64_vec(&mut out, 0);
        write_u64_vec(&mut out, 0);
        running += record.stored_len;
    }
    out.extend_from_slice(&strings);
    for payload in payloads { out.extend_from_slice(&payload); }
    if let Some(parent) = output.parent() { if !parent.as_os_str().is_empty() { fs::create_dir_all(parent).map_err(|e| format!("create parent '{}' failed: {e}", parent.display()))?; } }
    fs::write(output, out).map_err(|e| format!("write '{}' failed: {e}", output.display()))
}

pub fn parse(bytes: &[u8]) -> Result<ParsedPackage, String> {
    if bytes.len() < HEADER_LEN { return Err(format!("NEPAK header too small: {}", bytes.len())); }
    if bytes.get(0..4) != Some(MAGIC) { return Err("NEPAK magic mismatch".to_owned()); }
    let version = read_u16(bytes, 4)?;
    if version != VERSION { return Err(format!("unsupported NEPAK version {version}")); }
    let header_len = read_u16(bytes, 6)? as usize;
    if header_len != HEADER_LEN { return Err(format!("unsupported NEPAK header_len {header_len}")); }
    let count = read_u32(bytes, 8)? as usize;
    let table_offset = read_u64(bytes, 16)? as usize;
    let string_offset = read_u64(bytes, 24)? as usize;
    let string_len = read_u64(bytes, 32)? as usize;
    if table_offset.checked_add(count * ENTRY_LEN).ok_or("NEPAK table overflow")? > bytes.len() { return Err("NEPAK entry table outside file".to_owned()); }
    if string_offset.checked_add(string_len).ok_or("NEPAK string table overflow")? > bytes.len() { return Err("NEPAK string table outside file".to_owned()); }
    let strings = &bytes[string_offset..string_offset + string_len];
    let mut entries = Vec::with_capacity(count);
    for i in 0..count {
        let o = table_offset + i * ENTRY_LEN;
        let path_offset = read_u32(bytes, o + 8)?;
        let flags = read_u16(bytes, o + 12)?;
        let offset = read_u64(bytes, o + 16)?;
        let stored_len = read_u64(bytes, o + 24)?;
        let original_len = read_u64(bytes, o + 32)?;
        let hash = read_hash32(bytes, o + 40)?;
        let path = read_string(strings, path_offset)?;
        let end = (offset as usize).checked_add(stored_len as usize).ok_or("NEPAK payload range overflow")?;
        if end > bytes.len() { return Err(format!("NEPAK entry '{}' payload outside file", path)); }
        entries.push(PackageEntry { path, offset, stored_len, original_len, flags, hash });
    }
    Ok(ParsedPackage { entries })
}

pub fn inspect_json(bytes: &[u8], input: &Path) -> Result<serde_json::Value, String> {
    let parsed = parse(bytes)?;
    let entries = parsed.entries.iter().map(|e| json!({
        "path": e.path,
        "stored_len": e.stored_len,
        "original_len": e.original_len,
        "compressed": (e.flags & FLAG_DEFLATE) != 0,
        "hash_blake3": hex32(&e.hash),
    })).collect::<Vec<_>>();
    Ok(json!({
        "schema": "northstar.nepak.inspect.v1",
        "ok": true,
        "container": "NEPAK VFS package",
        "file": input.to_string_lossy().replace('\\', "/"),
        "entry_count": parsed.entries.len(),
        "entries": entries,
    }))
}

pub fn validate_bytes(bytes: &[u8]) -> Result<usize, String> {
    let parsed = parse(bytes)?;
    for entry in &parsed.entries {
        let raw = entry_payload(bytes, entry)?;
        if raw.len() as u64 != entry.original_len { return Err(format!("NEPAK entry '{}' original size mismatch", entry.path)); }
        if blake3::hash(&raw).as_bytes() != &entry.hash { return Err(format!("NEPAK entry '{}' hash mismatch", entry.path)); }
    }
    Ok(parsed.entries.len())
}

pub fn extract_to(bytes: &[u8], output_root: &Path, filter: Option<&str>, overwrite: bool) -> Result<usize, String> {
    let parsed = parse(bytes)?;
    let mut count = 0usize;
    for entry in &parsed.entries {
        if let Some(filter) = filter { if entry.path != filter { continue; } }
        let raw = entry_payload(bytes, entry)?;
        let out = safe_output_path(output_root, &entry.path)?;
        if out.exists() && !overwrite { return Err(format!("output '{}' exists; use --overwrite", out.display())); }
        if let Some(parent) = out.parent() { fs::create_dir_all(parent).map_err(|e| format!("create parent '{}' failed: {e}", parent.display()))?; }
        fs::write(&out, raw).map_err(|e| format!("write '{}' failed: {e}", out.display()))?;
        count += 1;
    }
    Ok(count)
}

fn entry_payload(bytes: &[u8], entry: &PackageEntry) -> Result<Vec<u8>, String> {
    let start = entry.offset as usize;
    let end = start.checked_add(entry.stored_len as usize).ok_or("NEPAK payload range overflow")?;
    let stored = bytes.get(start..end).ok_or_else(|| format!("NEPAK entry '{}' payload outside file", entry.path))?;
    if (entry.flags & FLAG_DEFLATE) != 0 { inflate(stored) } else { Ok(stored.to_vec()) }
}

struct BuildRecord { path: String, path_offset: u32, stored_len: u64, original_len: u64, flags: u16, hash: [u8; 32] }
fn stable_id_for_entries(records: &[BuildRecord]) -> u64 { let mut h = blake3::Hasher::new(); for r in records { h.update(r.path.as_bytes()); h.update(&r.hash); } u64::from_le_bytes(h.finalize().as_bytes()[0..8].try_into().unwrap()) }
fn stable_path_hash(path: &str) -> u64 { u64::from_le_bytes(blake3::hash(path.to_ascii_lowercase().as_bytes()).as_bytes()[0..8].try_into().unwrap()) }
fn push_string(strings: &mut Vec<u8>, value: &str) -> u32 { let o = strings.len() as u32; strings.extend_from_slice(value.as_bytes()); strings.push(0); o }
fn read_string(strings: &[u8], offset: u32) -> Result<String, String> { let s = offset as usize; if s >= strings.len() { return Err("NEPAK string offset outside table".to_owned()); } let n = strings[s..].iter().position(|b| *b == 0).ok_or("NEPAK string is not nul-terminated")?; String::from_utf8(strings[s..s+n].to_vec()).map_err(|e| format!("NEPAK path string is not UTF-8: {e}")) }
fn deflate(bytes: &[u8]) -> Result<Vec<u8>, String> { let mut e = DeflateEncoder::new(Vec::new(), Compression::default()); e.write_all(bytes).map_err(|e| e.to_string())?; e.finish().map_err(|e| e.to_string()) }
fn inflate(bytes: &[u8]) -> Result<Vec<u8>, String> { let mut d = DeflateDecoder::new(bytes); let mut out = Vec::new(); d.read_to_end(&mut out).map_err(|e| format!("deflate decode failed: {e}"))?; Ok(out) }
fn hex32(v: &[u8; 32]) -> String { v.iter().map(|b| format!("{b:02x}")).collect() }
fn write_u16(b: &mut [u8], o: usize, v: u16) { b[o..o+2].copy_from_slice(&v.to_le_bytes()); }
fn write_u32(b: &mut [u8], o: usize, v: u32) { b[o..o+4].copy_from_slice(&v.to_le_bytes()); }
fn write_u64(b: &mut [u8], o: usize, v: u64) { b[o..o+8].copy_from_slice(&v.to_le_bytes()); }
fn write_u16_vec(b: &mut Vec<u8>, v: u16) { b.extend_from_slice(&v.to_le_bytes()); }
fn write_u32_vec(b: &mut Vec<u8>, v: u32) { b.extend_from_slice(&v.to_le_bytes()); }
fn write_u64_vec(b: &mut Vec<u8>, v: u64) { b.extend_from_slice(&v.to_le_bytes()); }
fn read_u16(b: &[u8], o: usize) -> Result<u16, String> { let s = b.get(o..o+2).ok_or("truncated u16")?; Ok(u16::from_le_bytes(s.try_into().unwrap())) }
fn read_u32(b: &[u8], o: usize) -> Result<u32, String> { let s = b.get(o..o+4).ok_or("truncated u32")?; Ok(u32::from_le_bytes(s.try_into().unwrap())) }
fn read_u64(b: &[u8], o: usize) -> Result<u64, String> { let s = b.get(o..o+8).ok_or("truncated u64")?; Ok(u64::from_le_bytes(s.try_into().unwrap())) }
fn read_hash32(b: &[u8], o: usize) -> Result<[u8; 32], String> { let s = b.get(o..o+32).ok_or("truncated hash32")?; let mut out = [0u8; 32]; out.copy_from_slice(s); Ok(out) }
