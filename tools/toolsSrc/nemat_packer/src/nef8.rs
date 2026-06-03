use flate2::{read::DeflateDecoder, write::DeflateEncoder, Compression};
use serde_json::{json, Value};
use std::io::{Read, Write};

pub const HEADER_LEN: usize = 128;
pub const CONTENT_KIND_NEMAT: u16 = 4;
const FLAG_BODY_DEFLATE: u16 = 0x0001;
const COMPRESSION_DEFLATE: u16 = 1;

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
    pub schema_version: u64,
    body_hash: [u8; 32],
}

pub fn pack_nemat_xmltype(xml: &str, logical_path: &str, entry_count: u64) -> Result<Vec<u8>, String> {
    let body = xml.as_bytes();
    let compressed = deflate(body)?;
    let body_hash = blake3::hash(body);
    let logical_path = normalize_logical_path(logical_path);

    let mut out = vec![0u8; HEADER_LEN];
    out[0..4].copy_from_slice(b"NEF8");
    write_u16(&mut out, 4, 1);
    write_u16(&mut out, 6, HEADER_LEN as u16);
    write_u16(&mut out, 8, CONTENT_KIND_NEMAT);
    write_u16(&mut out, 10, FLAG_BODY_DEFLATE);
    write_u16(&mut out, 12, COMPRESSION_DEFLATE);
    write_u64(&mut out, 16, HEADER_LEN as u64);
    write_u64(&mut out, 24, compressed.len() as u64);
    write_u64(&mut out, 32, body.len() as u64);
    write_u64(&mut out, 40, entry_count);
    write_u64(&mut out, 48, 0);
    write_u64(&mut out, 56, 0);
    out[64..96].copy_from_slice(body_hash.as_bytes());
    write_u64(&mut out, 96, stable_u64(&logical_path));
    write_u64(&mut out, 104, stable_u64("northstar.nemat_packer.xmltype"));
    write_u64(&mut out, 112, 1);
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
        schema_version: read_u64(bytes, 112).unwrap_or(1),
    })
}

pub fn decode_nemat_xmltype(bytes: &[u8]) -> Result<String, String> {
    let header = parse_header(bytes)?;
    if header.version != 1 {
        return Err(format!("unsupported NEF8 version {}", header.version));
    }
    if header.header_len as usize != HEADER_LEN {
        return Err(format!("unsupported NEF8 header_len {}", header.header_len));
    }
    if header.content_kind != CONTENT_KIND_NEMAT {
        return Err(format!("NEF8 content_kind={} is not material_library ({})", header.content_kind, CONTENT_KIND_NEMAT));
    }
    if header.compression != COMPRESSION_DEFLATE || (header.flags & FLAG_BODY_DEFLATE) == 0 {
        return Err(format!("NEF8 .nemat requires deflate body flags=0x{:04x} compression={}", header.flags, header.compression));
    }
    let start = header.body_offset as usize;
    let end = start.checked_add(header.body_len as usize).ok_or("NEF8 body range overflow")?;
    let compressed = bytes.get(start..end).ok_or_else(|| format!("NEF8 body range outside file offset={} len={} file={}", header.body_offset, header.body_len, bytes.len()))?;
    let inflated = inflate(compressed)?;
    if inflated.len() as u64 != header.body_uncompressed_len {
        return Err(format!("NEF8 inflated body size mismatch actual={} expected={}", inflated.len(), header.body_uncompressed_len));
    }
    if blake3::hash(&inflated).as_bytes() != &header.body_hash {
        return Err("NEF8 body hash mismatch after inflate".to_owned());
    }
    let xml = String::from_utf8(inflated).map_err(|e| format!(".nemat XMLtype body is not UTF-8: {e}"))?;
    if !xml.trim_start().contains("<NematMaterialLibrary") {
        return Err(".nemat XMLtype body does not contain <NematMaterialLibrary>".to_owned());
    }
    Ok(xml)
}

pub fn inspect_nemat_json(bytes: &[u8], xmltype: Option<&str>) -> Result<Value, String> {
    let header = parse_header(bytes)?;
    let ok = header.content_kind == CONTENT_KIND_NEMAT;
    let mut value = json!({
        "schema": "northstar.nemat.inspect.v1",
        "ok": ok,
        "header": {
            "magic": "NEF8",
            "version": header.version,
            "header_len": header.header_len,
            "content_kind": header.content_kind,
            "content_kind_label": if ok { "material_library" } else { "non_nemat" },
            "flags": header.flags,
            "compression": header.compression,
            "entry_count": header.entry_count,
            "body_offset": header.body_offset,
            "body_len": header.body_len,
            "body_uncompressed_len": header.body_uncompressed_len,
            "stable_file_id": format!("{:016x}", header.stable_file_id),
            "schema_version": header.schema_version
        },
        "body": {
            "kind": "XMLtype",
            "root": "NematMaterialLibrary"
        }
    });
    if let Some(xml) = xmltype {
        value["xmltype"] = json!({
            "byte_len": xml.as_bytes().len(),
            "starts_with": xml.trim_start().lines().next().unwrap_or("")
        });
    }
    Ok(value)
}

pub fn normalize_logical_path(value: &str) -> String {
    value.trim().replace('\\', "/").trim_start_matches("./").trim_start_matches('/').to_owned()
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

pub fn stable_u64(value: &str) -> u64 {
    fnv1a64(value.as_bytes())
}

fn fnv1a64(bytes: &[u8]) -> u64 {
    const OFFSET: u64 = 0xcbf29ce484222325;
    const PRIME: u64 = 0x100000001b3;
    let mut hash = OFFSET;
    for byte in bytes {
        hash ^= *byte as u64;
        hash = hash.wrapping_mul(PRIME);
    }
    hash
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

    #[test]
    fn nemat_roundtrip_xmltype() {
        let xml = r#"<?xml version="1.0"?><NematMaterialLibrary schema="newengine.nemat.xmltype.v1"><Entries><Material name="m" shader="pbr.default"><Textures><Texture slot="base_color" ref="textures/a.ytd@a" /></Textures></Material></Entries></NematMaterialLibrary>"#;
        let bytes = pack_nemat_xmltype(xml, "materials/test.nemat", 1).unwrap();
        assert_eq!(decode_nemat_xmltype(&bytes).unwrap(), xml);
        assert_eq!(inspect_nemat_json(&bytes, Some(xml)).unwrap()["ok"], true);
    }

    #[test]
    fn nemat_rejects_bad_magic() {
        assert!(parse_header(b"BAD!").unwrap_err().contains("header too small"));
    }
}
