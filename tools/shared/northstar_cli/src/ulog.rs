use northstar_logging::{JsonlUlogSink, UlogEmitter};
use northstar_ulog::{UlogEvent, UlogLevel};
use std::{env, error::Error, path::PathBuf, time::Instant};

#[derive(Clone)]
pub struct ToolRunInstrumentation {
    tool_name: String,
    command: String,
    run_id: String,
    emitter: Option<UlogEmitter>,
    started_at: Instant,
}

impl ToolRunInstrumentation {
    pub fn start(tool_name: impl Into<String>, command: impl Into<String>, args: &[String]) -> Self {
        let tool_name = tool_name.into();
        let command = command.into();
        let run_id = run_id();
        let emitter = ulog_path_from_args(args)
            .or_else(|| env::var_os("NORTHSTAR_ULOG").map(PathBuf::from))
            .map(|path| UlogEmitter::new().with_sink(JsonlUlogSink::new(path)));
        let this = Self { tool_name, command, run_id, emitter, started_at: Instant::now() };
        let _ = this.emit(UlogLevel::Info, "tool.command.started", "Command started");
        this
    }

    pub fn doctor_started(&self) { let _ = self.emit(UlogLevel::Info, "tool.doctor.started", "Doctor started"); }
    pub fn doctor_completed(&self) { let _ = self.emit(UlogLevel::Ok, "tool.doctor.completed", "Doctor completed"); }
    pub fn asset_validate_started(&self) { let _ = self.emit(UlogLevel::Info, "asset.validate.started", "Asset validation started"); }
    pub fn asset_validate_completed(&self) { let _ = self.emit(UlogLevel::Ok, "asset.validate.completed", "Asset validation completed"); }
    pub fn asset_validate_failed(&self) { let _ = self.emit(UlogLevel::Error, "asset.validate.failed", "Asset validation failed"); }

    pub fn complete(&self) {
        let _ = self.emit_with_duration(UlogLevel::Ok, "tool.command.completed", "Command completed");
    }

    pub fn failed(&self, message: impl AsRef<str>) {
        let _ = self.emit_with_duration(UlogLevel::Error, "tool.command.failed", message.as_ref());
    }

    pub fn emit(&self, level: UlogLevel, event_id: &str, message: &str) -> Result<(), Box<dyn Error>> {
        if let Some(emitter) = &self.emitter {
            let event = UlogEvent::new(level, event_id, message, "tool", &self.tool_name, &self.run_id)
                .with_field("command", self.command.clone());
            emitter.emit(event)?;
        }
        Ok(())
    }

    fn emit_with_duration(&self, level: UlogLevel, event_id: &str, message: &str) -> Result<(), Box<dyn Error>> {
        if let Some(emitter) = &self.emitter {
            let event = UlogEvent::new(level, event_id, message, "tool", &self.tool_name, &self.run_id)
                .with_field("command", self.command.clone())
                .with_field("duration_ms", self.started_at.elapsed().as_millis() as u64);
            emitter.emit(event)?;
        }
        Ok(())
    }
}

pub fn strip_ulog_args(args: Vec<String>) -> Vec<String> {
    let mut out = Vec::new();
    let mut skip = false;
    for arg in args {
        if skip { skip = false; continue; }
        if arg == "--ulog" { skip = true; continue; }
        if arg.starts_with("--ulog=") { continue; }
        out.push(arg);
    }
    out
}

fn ulog_path_from_args(args: &[String]) -> Option<PathBuf> {
    let mut iter = args.iter();
    while let Some(arg) = iter.next() {
        if arg == "--ulog" { return iter.next().map(PathBuf::from); }
        if let Some(value) = arg.strip_prefix("--ulog=") { return Some(PathBuf::from(value)); }
    }
    None
}

fn run_id() -> String {
    use std::time::{SystemTime, UNIX_EPOCH};
    let ms = SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default().as_millis();
    format!("RUN-{ms}")
}
