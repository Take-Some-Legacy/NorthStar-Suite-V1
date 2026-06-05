use crate::sink::UlogSink;
use northstar_ulog::{append_jsonl_event, UlogEvent};
use std::{error::Error, path::{Path, PathBuf}};

#[derive(Clone, Debug)]
pub struct JsonlUlogSink {
    path: PathBuf,
}

impl JsonlUlogSink {
    pub fn new(path: impl AsRef<Path>) -> Self { Self { path: path.as_ref().to_path_buf() } }
    pub fn path(&self) -> &Path { &self.path }
}

impl UlogSink for JsonlUlogSink {
    fn emit(&self, event: &UlogEvent) -> Result<(), Box<dyn Error>> {
        append_jsonl_event(&self.path, event)
    }
}
