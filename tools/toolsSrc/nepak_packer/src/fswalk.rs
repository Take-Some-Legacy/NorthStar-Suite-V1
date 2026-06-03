use std::fs;
use std::path::{Path, PathBuf};

#[derive(Debug, Clone)]
pub struct SourceFile {
    pub disk_path: PathBuf,
    pub package_path: String,
}

pub fn collect_sources(input: &Path) -> Result<Vec<SourceFile>, String> {
    if input.is_file() {
        let name = input.file_name().and_then(|x| x.to_str()).ok_or_else(|| format!("invalid file name '{}'", input.display()))?;
        return Ok(vec![SourceFile { disk_path: input.to_path_buf(), package_path: normalize_package_path(name) }]);
    }
    if !input.is_dir() { return Err(format!("input '{}' is neither file nor directory", input.display())); }
    let mut out = Vec::new();
    walk_dir(input, input, &mut out)?;
    out.sort_by(|a, b| a.package_path.cmp(&b.package_path));
    Ok(out)
}

fn walk_dir(root: &Path, dir: &Path, out: &mut Vec<SourceFile>) -> Result<(), String> {
    for entry in fs::read_dir(dir).map_err(|e| format!("read_dir '{}' failed: {e}", dir.display()))? {
        let entry = entry.map_err(|e| e.to_string())?;
        let path = entry.path();
        if path.is_dir() { walk_dir(root, &path, out)?; }
        else if path.is_file() {
            let rel = path.strip_prefix(root).unwrap_or(&path);
            let package_path = normalize_package_path(&rel.to_string_lossy());
            out.push(SourceFile { disk_path: path, package_path });
        }
    }
    Ok(())
}

pub fn normalize_package_path(value: &str) -> String {
    let mut out = value.replace('\\', "/").trim_start_matches('/').trim_start_matches("./").to_owned();
    while out.contains("//") { out = out.replace("//", "/"); }
    out
}

pub fn safe_output_path(root: &Path, package_path: &str) -> Result<PathBuf, String> {
    let normalized = normalize_package_path(package_path);
    if normalized.is_empty() || normalized.contains("../") || normalized.starts_with("../") || normalized.contains(':') {
        return Err(format!("unsafe package path '{package_path}'"));
    }
    Ok(root.join(normalized))
}
