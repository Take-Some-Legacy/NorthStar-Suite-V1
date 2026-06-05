use crate::{validate_event, UlogEvent};
use std::{fs::OpenOptions, io::{self, Write}, path::Path};

pub fn write_jsonl_event(mut writer: impl Write, event: &UlogEvent) -> Result<(), Box<dyn std::error::Error>> {
    validate_event(event)?;
    serde_json::to_writer(&mut writer, event)?;
    writer.write_all(b"\n")?;
    Ok(())
}

pub fn append_jsonl_event(path: impl AsRef<Path>, event: &UlogEvent) -> Result<(), Box<dyn std::error::Error>> {
    let path = path.as_ref();
    if let Some(parent) = path.parent() {
        if !parent.as_os_str().is_empty() { std::fs::create_dir_all(parent)?; }
    }
    let file = OpenOptions::new().create(true).append(true).open(path)?;
    write_jsonl_event(io::BufWriter::new(file), event)
}
