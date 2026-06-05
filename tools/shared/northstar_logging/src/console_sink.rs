use crate::sink::UlogSink;
use northstar_ulog::{UlogEvent, UlogLevel};
use std::error::Error;

#[derive(Clone, Copy, Debug, Default)]
pub struct ConsoleStatusSink;

impl UlogSink for ConsoleStatusSink {
    fn emit(&self, event: &UlogEvent) -> Result<(), Box<dyn Error>> {
        let msg = format!("{} {}", event.event_id, event.message);
        match event.level {
            UlogLevel::Trace | UlogLevel::Debug | UlogLevel::Info => status_stdout("INFO", msg),
            UlogLevel::Ok => status_stdout("OK", msg),
            UlogLevel::Warn => status_stdout("WARN", msg),
            UlogLevel::Error | UlogLevel::Fatal => status_stderr("ERROR", msg),
        }
        Ok(())
    }
}

fn status_stdout(tag: &str, message: impl AsRef<str>) {
    println!("[{tag}] {}", message.as_ref());
}

fn status_stderr(tag: &str, message: impl AsRef<str>) {
    eprintln!("[{tag}] {}", message.as_ref());
}
