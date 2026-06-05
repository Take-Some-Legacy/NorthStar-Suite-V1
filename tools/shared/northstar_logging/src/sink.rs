use northstar_ulog::{UlogEvent, UlogLevel};
use std::{error::Error, sync::Arc};

pub trait UlogSink: Send + Sync {
    fn emit(&self, event: &UlogEvent) -> Result<(), Box<dyn Error>>;
}

#[derive(Clone, Default)]
pub struct UlogEmitter {
    sinks: Vec<Arc<dyn UlogSink>>,
}

impl UlogEmitter {
    pub fn new() -> Self { Self { sinks: Vec::new() } }

    pub fn with_sink(mut self, sink: impl UlogSink + 'static) -> Self {
        self.sinks.push(Arc::new(sink));
        self
    }

    pub fn add_sink(&mut self, sink: impl UlogSink + 'static) {
        self.sinks.push(Arc::new(sink));
    }

    pub fn emit(&self, event: UlogEvent) -> Result<(), Box<dyn Error>> {
        for sink in &self.sinks {
            sink.emit(&event)?;
        }
        Ok(())
    }
}

pub fn emit_legacy(emitter: &UlogEmitter, level: UlogLevel, message: impl Into<String>, source_name: impl Into<String>, run_id: impl Into<String>) -> Result<(), Box<dyn Error>> {
    let message = message.into();
    let event_id = match level {
        UlogLevel::Trace => "legacy.trace",
        UlogLevel::Debug => "legacy.debug",
        UlogLevel::Info => "legacy.info",
        UlogLevel::Ok => "legacy.ok",
        UlogLevel::Warn => "legacy.warn",
        UlogLevel::Error => "legacy.error",
        UlogLevel::Fatal => "legacy.fatal",
    };
    emitter.emit(UlogEvent::new(level, event_id, message, "tool", source_name, run_id))
}
