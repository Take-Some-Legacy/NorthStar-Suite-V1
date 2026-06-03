use newengine_texture_container::{
    texture_payload_len, TextureEncodedBuildEntry, TextureEncodedMipData,
    PIXEL_FORMAT_BC1_RGBA_SRGB, PIXEL_FORMAT_BC1_RGBA_UNORM,
    PIXEL_FORMAT_BC2_RGBA_SRGB, PIXEL_FORMAT_BC2_RGBA_UNORM,
    PIXEL_FORMAT_BC3_RGBA_SRGB, PIXEL_FORMAT_BC3_RGBA_UNORM,
    PIXEL_FORMAT_BC5_RG_UNORM, PIXEL_FORMAT_BC6H_SF16,
    PIXEL_FORMAT_BC6H_UF16, PIXEL_FORMAT_BC7_RGBA_SRGB,
    PIXEL_FORMAT_BC7_RGBA_UNORM, PIXEL_FORMAT_RGBA8_SRGB,
    PIXEL_FORMAT_RGBA8_UNORM,
};
use std::{fs, path::Path};

pub fn load(name: String, path: &Path, srgb: bool, no_mips: bool) -> Result<TextureEncodedBuildEntry, String> {
    let bytes = fs::read(path).map_err(|e| format!("read '{}' failed: {e}", path.display()))?;
    let mut dds = parse_dds(&bytes).map_err(|e| format!("DDS import '{}' failed: {e}", path.display()))?;
    if no_mips && dds.mips.len() > 1 {
        dds.mips.truncate(1);
    }
    if srgb {
        dds.format = force_srgb_format(&dds.format);
        dds.color_space = "srgb".to_owned();
    }
    println!("[OK] source DDS: {} {}x{} format={} mips={}", path.display(), dds.width, dds.height, dds.format, dds.mips.len());
    Ok(TextureEncodedBuildEntry { name, width: dds.width, height: dds.height, format: dds.format, color_space: dds.color_space, mips: dds.mips })
}

struct DdsImport {
    width: u32,
    height: u32,
    format: String,
    color_space: String,
    mips: Vec<TextureEncodedMipData>,
}

fn parse_dds(bytes: &[u8]) -> Result<DdsImport, String> {
    if bytes.len() < 128 || bytes.get(0..4) != Some(b"DDS ") {
        return Err("missing DDS magic/header".to_owned());
    }
    let header_size = read_u32(bytes, 4)?;
    if header_size != 124 {
        return Err(format!("unsupported DDS header size {header_size}"));
    }
    let height = read_u32(bytes, 12)?;
    let width = read_u32(bytes, 16)?;
    let mip_count = read_u32(bytes, 28)?.max(1);
    let pf_size = read_u32(bytes, 76)?;
    if pf_size != 32 {
        return Err(format!("unsupported DDS pixel format size {pf_size}"));
    }
    let pf_flags = read_u32(bytes, 80)?;
    let fourcc = read_fourcc(bytes, 84)?;
    let rgb_bit_count = read_u32(bytes, 88)?;
    let r_mask = read_u32(bytes, 92)?;
    let g_mask = read_u32(bytes, 96)?;
    let b_mask = read_u32(bytes, 100)?;
    let a_mask = read_u32(bytes, 104)?;

    let mut data_offset = 128usize;
    let format = if (pf_flags & 0x0000_0004) != 0 {
        match &fourcc {
            b"DXT1" => PIXEL_FORMAT_BC1_RGBA_UNORM.to_owned(),
            b"DXT3" => PIXEL_FORMAT_BC2_RGBA_UNORM.to_owned(),
            b"DXT5" => PIXEL_FORMAT_BC3_RGBA_UNORM.to_owned(),
            b"ATI2" | b"BC5U" => PIXEL_FORMAT_BC5_RG_UNORM.to_owned(),
            b"DX10" => {
                if bytes.len() < 148 {
                    return Err("DDS DX10 header is truncated".to_owned());
                }
                data_offset = 148;
                let dxgi = read_u32(bytes, 128)?;
                dxgi_to_format(dxgi)?.to_owned()
            }
            other => return Err(format!("unsupported DDS FourCC '{}'; supported: DXT1, DXT3, DXT5, ATI2/BC5U, DX10 BC1/BC2/BC3/BC5/BC6H/BC7/RGBA8", String::from_utf8_lossy(other))),
        }
    } else if (pf_flags & 0x0000_0040) != 0 && rgb_bit_count == 32 {
        if r_mask == 0x0000_00ff && g_mask == 0x0000_ff00 && b_mask == 0x00ff_0000 && a_mask == 0xff00_0000 {
            PIXEL_FORMAT_RGBA8_UNORM.to_owned()
        } else if r_mask == 0x00ff_0000 && g_mask == 0x0000_ff00 && b_mask == 0x0000_00ff && a_mask == 0xff00_0000 {
            return Err("DDS BGRA8 import is not supported yet; convert to RGBA8 or DX10 R8G8B8A8".to_owned());
        } else {
            return Err(format!("unsupported DDS 32-bit masks r={r_mask:#x} g={g_mask:#x} b={b_mask:#x} a={a_mask:#x}"));
        }
    } else {
        return Err(format!("unsupported DDS pixel format flags={pf_flags:#x} rgb_bits={rgb_bit_count}"));
    };

    let color_space = if format.ends_with("_SRGB") { "srgb" } else { "linear" }.to_owned();
    let mut offset = data_offset;
    let mut mips = Vec::new();
    let mut w = width;
    let mut h = height;
    for level in 0..mip_count {
        let len = texture_payload_len(&format, w, h).map_err(|e| format!("DDS mip payload length failed: {e}"))?;
        let end = offset.checked_add(len).ok_or("DDS payload offset overflow")?;
        let payload = bytes.get(offset..end).ok_or_else(|| format!("DDS payload truncated at mip {level}; need {len} bytes"))?;
        mips.push(TextureEncodedMipData { level, width: w, height: h, bytes: payload.to_vec() });
        offset = end;
        w = (w / 2).max(1);
        h = (h / 2).max(1);
    }
    Ok(DdsImport { width, height, format, color_space, mips })
}

fn dxgi_to_format(dxgi: u32) -> Result<&'static str, String> {
    match dxgi {
        28 => Ok(PIXEL_FORMAT_RGBA8_UNORM),
        29 => Ok(PIXEL_FORMAT_RGBA8_SRGB),
        71 => Ok(PIXEL_FORMAT_BC1_RGBA_UNORM),
        72 => Ok(PIXEL_FORMAT_BC1_RGBA_SRGB),
        74 => Ok(PIXEL_FORMAT_BC2_RGBA_UNORM),
        75 => Ok(PIXEL_FORMAT_BC2_RGBA_SRGB),
        77 => Ok(PIXEL_FORMAT_BC3_RGBA_UNORM),
        78 => Ok(PIXEL_FORMAT_BC3_RGBA_SRGB),
        83 => Ok(PIXEL_FORMAT_BC5_RG_UNORM),
        95 => Ok(PIXEL_FORMAT_BC6H_UF16),
        96 => Ok(PIXEL_FORMAT_BC6H_SF16),
        98 => Ok(PIXEL_FORMAT_BC7_RGBA_UNORM),
        99 => Ok(PIXEL_FORMAT_BC7_RGBA_SRGB),
        other => Err(format!("unsupported DXGI format {other}; supported RGBA8, BC1, BC2, BC3, BC5, BC6H, BC7")),
    }
}

fn force_srgb_format(format: &str) -> String {
    match format {
        PIXEL_FORMAT_RGBA8_UNORM => PIXEL_FORMAT_RGBA8_SRGB.to_owned(),
        PIXEL_FORMAT_BC1_RGBA_UNORM => PIXEL_FORMAT_BC1_RGBA_SRGB.to_owned(),
        PIXEL_FORMAT_BC2_RGBA_UNORM => PIXEL_FORMAT_BC2_RGBA_SRGB.to_owned(),
        PIXEL_FORMAT_BC3_RGBA_UNORM => PIXEL_FORMAT_BC3_RGBA_SRGB.to_owned(),
        PIXEL_FORMAT_BC7_RGBA_UNORM => PIXEL_FORMAT_BC7_RGBA_SRGB.to_owned(),
        other => other.to_owned(),
    }
}

fn read_u32(bytes: &[u8], offset: usize) -> Result<u32, String> {
    let slice = bytes.get(offset..offset + 4).ok_or_else(|| format!("DDS header truncated at u32 offset {offset}"))?;
    Ok(u32::from_le_bytes([slice[0], slice[1], slice[2], slice[3]]))
}

fn read_fourcc(bytes: &[u8], offset: usize) -> Result<[u8; 4], String> {
    let slice = bytes.get(offset..offset + 4).ok_or_else(|| format!("DDS header truncated at FourCC offset {offset}"))?;
    Ok([slice[0], slice[1], slice[2], slice[3]])
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn force_srgb_preserves_linear_only_bc5() {
        assert_eq!(force_srgb_format(PIXEL_FORMAT_BC5_RG_UNORM), PIXEL_FORMAT_BC5_RG_UNORM);
    }
}
