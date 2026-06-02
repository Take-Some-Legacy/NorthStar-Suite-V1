use image::GenericImageView;
use newengine_texture_container::{generate_rgba8_mips, TextureBuildEntry, TextureMipData};
use std::{fs, path::{Path, PathBuf}};

pub fn collect_sources(input_dir: Option<&Path>, specs: &[String]) -> Result<Vec<(String, PathBuf)>, String> {
    let mut out = specs.iter().map(|spec| parse_texture_spec(spec)).collect::<Vec<_>>();
    if let Some(dir) = input_dir {
        for entry in fs::read_dir(dir).map_err(|e| format!("read_dir '{}' failed: {e}", dir.display()))? {
            let path = entry.map_err(|e| e.to_string())?.path();
            if path.is_file() && is_supported_source_image(&path) {
                let name = path.file_stem().and_then(|v| v.to_str()).unwrap_or("texture").to_owned();
                out.push((name, path));
            }
        }
    }
    out.sort_by(|a, b| a.0.cmp(&b.0));
    out.dedup_by(|a, b| a.0.eq_ignore_ascii_case(&b.0));
    Ok(out)
}

pub fn load_texture_entry(name: String, path: PathBuf, srgb: bool, no_mips: bool) -> Result<TextureBuildEntry, String> {
    let img = image::open(&path).map_err(|e| format!("image decode '{}' failed: {e}", path.display()))?;
    let (width, height) = img.dimensions();
    let rgba = img.to_rgba8().into_raw();
    let mips = if no_mips {
        vec![TextureMipData { level: 0, width, height, rgba }]
    } else {
        generate_rgba8_mips(width, height, rgba).map_err(|e| format!("mip generation '{name}' failed: {e}"))?
    };
    println!("[OK] source texture: {} {}x{} mips={}", path.display(), width, height, mips.len());
    Ok(TextureBuildEntry {
        name,
        width,
        height,
        color_space: if srgb { "srgb" } else { "linear" }.to_owned(),
        mips,
    })
}

pub fn normalize_logical_path(value: &str) -> String {
    value.trim().replace('\\', "/").trim_start_matches("./").trim_start_matches('/').to_owned()
}

pub fn sanitize_file_name(value: &str) -> String {
    value.chars().map(|c| if c.is_ascii_alphanumeric() || c == '-' || c == '_' || c == '.' { c } else { '_' }).collect()
}

fn parse_texture_spec(spec: &str) -> (String, PathBuf) {
    if let Some((name, path)) = spec.split_once('=') {
        (name.to_owned(), PathBuf::from(path))
    } else {
        let path = PathBuf::from(spec);
        let name = path.file_stem().and_then(|v| v.to_str()).unwrap_or("texture").to_owned();
        (name, path)
    }
}

fn is_supported_source_image(path: &Path) -> bool {
    matches!(
        path.extension().and_then(|v| v.to_str()).map(|v| v.to_ascii_lowercase()).as_deref(),
        Some("png" | "jpg" | "jpeg" | "tga" | "bmp" | "webp")
    )
}
