use crate::{validate_event, UlogEvent};
use std::{fs::File, io::{BufRead, BufReader, Read}, path::Path};

#[derive(Clone, Debug, Default)]
pub struct UlogReadReport {
    pub events: Vec<UlogEvent>,
    pub warnings: Vec<String>,
    pub total_lines: usize,
}

pub fn read_jsonl_file(path: impl AsRef<Path>) -> Result<UlogReadReport, String> {
    let file = File::open(path.as_ref()).map_err(|e| format!("read '{}' failed: {e}", path.as_ref().display()))?;
    read_jsonl_reader(file)
}

pub fn read_jsonl_reader(reader: impl Read) -> Result<UlogReadReport, String> {
    let mut report = UlogReadReport::default();
    for (idx, line) in BufReader::new(reader).lines().enumerate() {
        let line_no = idx + 1;
        report.total_lines = line_no;
        let line = line.map_err(|e| format!("read line {line_no} failed: {e}"))?;
        if line.trim().is_empty() { continue; }
        match serde_json::from_str::<UlogEvent>(&line) {
            Ok(event) => match validate_event(&event) {
                Ok(()) => report.events.push(event),
                Err(err) => report.warnings.push(format!("invalid event skipped line={line_no} reason={err}")),
            },
            Err(err) => report.warnings.push(format!("invalid JSON line skipped line={line_no} reason={err}")),
        }
    }
    if report.events.is_empty() {
        return Err("file contains no valid events".to_owned());
    }
    Ok(report)
}
