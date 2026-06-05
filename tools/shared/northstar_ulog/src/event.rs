use crate::{schema::ULOG_EVENT_SCHEMA_V1, UlogLevel};
use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct UlogSource {
    pub kind: String,
    pub name: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub version: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub provider_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub gateway_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub capability_id: Option<String>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct UlogLocation {
    #[serde(skip_serializing_if = "Option::is_none")]
    pub file: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub line: Option<u32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub module: Option<String>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct UlogContext {
    pub run_id: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub session_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub trace_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub span_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub parent_span_id: Option<String>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct UlogEvent {
    pub schema: String,
    pub timestamp_utc: String,
    pub level: UlogLevel,
    pub event_id: String,
    pub message: String,
    pub source: UlogSource,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub location: Option<UlogLocation>,
    pub context: UlogContext,
    #[serde(default, skip_serializing_if = "Value::is_null")]
    pub fields: Value,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub diagnostic: Option<Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error: Option<Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub asset: Option<Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub route: Option<Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub performance: Option<Value>,
}

impl UlogEvent {
    pub fn new(level: UlogLevel, event_id: impl Into<String>, message: impl Into<String>, source_kind: impl Into<String>, source_name: impl Into<String>, run_id: impl Into<String>) -> Self {
        Self {
            schema: ULOG_EVENT_SCHEMA_V1.to_owned(),
            timestamp_utc: timestamp_utc_now(),
            level,
            event_id: event_id.into(),
            message: message.into(),
            source: UlogSource {
                kind: source_kind.into(),
                name: source_name.into(),
                version: None,
                provider_id: None,
                gateway_id: None,
                capability_id: None,
            },
            location: None,
            context: UlogContext {
                run_id: run_id.into(),
                session_id: None,
                trace_id: None,
                span_id: None,
                parent_span_id: None,
            },
            fields: Value::Object(Map::new()),
            diagnostic: None,
            error: None,
            asset: None,
            route: None,
            performance: None,
        }
    }

    pub fn with_field(mut self, key: impl Into<String>, value: impl Into<Value>) -> Self {
        if !self.fields.is_object() {
            self.fields = Value::Object(Map::new());
        }
        if let Some(fields) = self.fields.as_object_mut() {
            fields.insert(key.into(), value.into());
        }
        self
    }
}

pub fn timestamp_utc_now() -> String {
    use std::time::{SystemTime, UNIX_EPOCH};
    let now = SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default();
    let secs = now.as_secs();
    let millis = now.subsec_millis();
    let days = (secs / 86_400) as i64;
    let sod = secs % 86_400;
    let (year, month, day) = civil_from_days(days);
    let hour = sod / 3_600;
    let minute = (sod % 3_600) / 60;
    let second = sod % 60;
    format!("{year:04}-{month:02}-{day:02}T{hour:02}:{minute:02}:{second:02}.{millis:03}Z")
}

fn civil_from_days(days_since_unix_epoch: i64) -> (i32, u32, u32) {
    let z = days_since_unix_epoch + 719_468;
    let era = if z >= 0 { z } else { z - 146_096 } / 146_097;
    let doe = z - era * 146_097;
    let yoe = (doe - doe / 1_460 + doe / 36_524 - doe / 146_096) / 365;
    let y = yoe + era * 400;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let d = doy - (153 * mp + 2) / 5 + 1;
    let m = mp + if mp < 10 { 3 } else { -9 };
    let year = y + if m <= 2 { 1 } else { 0 };
    (year as i32, m as u32, d as u32)
}
