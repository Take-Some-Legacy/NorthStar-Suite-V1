use flate2::{read::DeflateDecoder, write::DeflateEncoder, Compression};
use newengine_texture_container::parse_manifest_only;
use std::io::{Read, Write};

pub const HEADER_LEN: usize = 128;
pub const CONTENT_KIND_YTD: u16 = 1;
const FLAG_BODY_DEFLATE: u16 = 0x0001;
const COMPRESSION_DEFLATE: u16 = 1;

#[derive(Debug, Clone)]
pub struct Nef8Header {
    pub content_kind: u16,
    pub body_offset: u64,
    pub body_len: u64,
    pub body_uncompressed_len: u64,
    pub entry_count: u64,
    body_hash: [u8; 32],
}

pub fn pack_ytd(body: &[u8], logical_path: &str, schema_version: u64) -> Result<Vec<u8>, String> {
    let compressed = deflate(body)?;
    let hash = blake3::hash(body);
    let mut out = vec![0u8; HEADER_LEN];
    out[0..4].copy_from_slice(b"NEF8");
    write_u16(&mut out, 4, 1);
    write_u16(&mut out, 6, HEADER_LEN as u16);
    write_u16(&mut out, 8, CONTENT_KIND_YTD);
    write_u16(&mut out, 10, FLAG_BODY_DEFLATE);
    write_u16(&mut out, 12, COMPRESSION_DEFLATE);
    write_u64(&mut out, 16, HEADER_LEN as u64);
    write_u64(&mut out, 24, compressed.len() as u64);
    write_u64(&mut out, 32, body.len() as u64);
    let entry_count = parse_manifest_only(body).map(|m| m.entries.len() as u64).unwrap_or(1);
    write_u64(&mut out, 40, entry_count);
    out[64..96].copy_from_slice(hash.as_bytes());
    write_u64(&mut out, 96, stable_u64(logical_path));
    write_u64(&mut out, 104, stable_u64("northstar.ytd_packer"));
    write_u64(&mut out, 112, schema_version);
    out.extend_from_slice(&compressed);
    Ok(out)
}

pub fn parse_header(bytes: &[u8]) -> Result<Nef8Header, String> {
    if bytes.len() < HEADER_LEN {
        return Err(format!("NEF8 header too small: bytes={} expected>={}", bytes.len(), HEADER_LEN));
    }
    if bytes.get(0..4) != Some(b"NEF8") {
        return Err("NEF8 magic mismatch".to_owned());
    }
    let flags = read_u16(bytes, 10)?;
    let compression = read_u16(bytes, 12)?;
    if (flags & FLAG_BODY_DEFLATE) == 0 || compression != COMPRESSION_DEFLATE {
        return Err(format!("unsupported NEF8 body flags=0x{flags:04x} compression={compression}"));
    }
    Ok(Nef8Header {
        content_kind: read_u16(bytes, 8)?,
        body_offset: read_u64(bytes, 16)?,
        body_len: read_u64(bytes, 24)?,
        body_uncompressed_len: read_u64(bytes, 32)?,
        entry_count: read_u64(bytes, 40)?,
        body_hash: read_hash32(bytes, 64)?,
    })
}

pub fn decode_ytd_body(bytes: &[u8], header: &Nef8Header) -> Result<Vec<u8>, String> {
    if header.content_kind != CONTENT_KIND_YTD {
        return Err(format!("not a .ytd NEF8 content_kind={} expected={}", header.content_kind, CONTENT_KIND_YTD));
    }
    let start = header.body_offset as usize;
    let end = start.checked_add(header.body_len as usize).ok_or("NEF8 body range overflow")?;
    let compressed = bytes.get(start..end).ok_or_else(|| {
        format!("NEF8 body range outside file offset={} len={} file={}", header.body_offset, header.body_len, bytes.len())
    })?;
    let body = inflate(compressed)?;
    if body.len() as u64 != header.body_uncompressed_len {
        return Err(format!("NEF8 inflated body size mismatch actual={} expected={}", body.len(), header.body_uncompressed_len));
    }
    if blake3::hash(&body).as_bytes() != &header.body_hash {
        return Err("NEF8 body hash mismatch".to_owned());
    }
    if body.get(0..4) != Some(b"NETD") {
        return Err("YTD body is not NETD texture dictionary payload".to_owned());
    }
    Ok(body)
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

fn stable_u64(value: &str) -> u64 {
    let h = blake3::hash(value.as_bytes());
    u64::from_le_bytes(h.as_bytes()[0..8].try_into().expect("hash slice"))
}

fn write_u16(out: &mut [u8], offset: usize, value: u16) { out[offset..offset + 2].copy_from_slice(&value.to_le_bytes()); }
fn write_u64(out: &mut [u8], offset: usize, value: u64) { out[offset..offset + 8].copy_from_slice(&value.to_le_bytes()); }
fn read_u16(bytes: &[u8], offset: usize) -> Result<u16, String> {
    let slice = bytes.get(offset..offset + 2).ok_or_else(|| format!("header truncated at u16 offset {offset}"))?;
    Ok(u16::from_le_bytes([slice[0], slice[1]]))
}
fn read_u64(bytes: &[u8], offset: usize) -> Result<u64, String> {
    let slice = bytes.get(offset..offset + 8).ok_or_else(|| format!("header truncated at u64 offset {offset}"))?;
    Ok(u64::from_le_bytes([slice[0], slice[1], slice[2], slice[3], slice[4], slice[5], slice[6], slice[7]]))
}
fn read_hash32(bytes: &[u8], offset: usize) -> Result<[u8; 32], String> {
    let slice = bytes.get(offset..offset + 32).ok_or_else(|| format!("header truncated at hash32 offset {offset}"))?;
    let mut out = [0u8; 32];
    out.copy_from_slice(slice);
    Ok(out)
}
