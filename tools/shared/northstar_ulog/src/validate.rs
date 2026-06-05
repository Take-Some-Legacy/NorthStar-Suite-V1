use crate::{schema::ULOG_EVENT_SCHEMA_V1, UlogEvent};
use std::{error::Error, fmt};

#[derive(Clone, Debug)]
pub struct UlogValidationError {
    pub message: String,
}

impl UlogValidationError {
    pub fn new(message: impl Into<String>) -> Self { Self { message: message.into() } }
}

impl fmt::Display for UlogValidationError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result { f.write_str(&self.message) }
}

impl Error for UlogValidationError {}

pub fn validate_event(event: &UlogEvent) -> Result<(), UlogValidationError> {
    if event.schema != ULOG_EVENT_SCHEMA_V1 {
        return Err(UlogValidationError::new(format!("unknown schema '{}'", event.schema)));
    }
    if event.timestamp_utc.trim().is_empty() || !event.timestamp_utc.ends_with('Z') || !event.timestamp_utc.contains('T') {
        return Err(UlogValidationError::new("invalid timestamp_utc"));
    }
    if event.event_id.trim().is_empty() {
        return Err(UlogValidationError::new("missing event_id"));
    }
    if event.message.trim().is_empty() {
        return Err(UlogValidationError::new("missing message"));
    }
    if event.source.kind.trim().is_empty() {
        return Err(UlogValidationError::new("missing source.kind"));
    }
    if event.source.name.trim().is_empty() {
        return Err(UlogValidationError::new("missing source.name"));
    }
    if event.context.run_id.trim().is_empty() {
        return Err(UlogValidationError::new("missing context.run_id"));
    }
    Ok(())
}
