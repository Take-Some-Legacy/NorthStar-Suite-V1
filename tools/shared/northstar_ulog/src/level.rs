use serde::{Deserialize, Serialize};
use std::{fmt, str::FromStr};

#[derive(Clone, Copy, Debug, Eq, PartialEq, Ord, PartialOrd, Hash, Serialize, Deserialize)]
#[serde(rename_all = "UPPERCASE")]
pub enum UlogLevel {
    Trace,
    Debug,
    Info,
    Ok,
    Warn,
    Error,
    Fatal,
}

impl UlogLevel {
    pub const ALL: [UlogLevel; 7] = [
        UlogLevel::Trace,
        UlogLevel::Debug,
        UlogLevel::Info,
        UlogLevel::Ok,
        UlogLevel::Warn,
        UlogLevel::Error,
        UlogLevel::Fatal,
    ];

    pub fn as_str(self) -> &'static str {
        match self {
            UlogLevel::Trace => "TRACE",
            UlogLevel::Debug => "DEBUG",
            UlogLevel::Info => "INFO",
            UlogLevel::Ok => "OK",
            UlogLevel::Warn => "WARN",
            UlogLevel::Error => "ERROR",
            UlogLevel::Fatal => "FATAL",
        }
    }
}

impl fmt::Display for UlogLevel {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(self.as_str())
    }
}

impl FromStr for UlogLevel {
    type Err = String;

    fn from_str(value: &str) -> Result<Self, Self::Err> {
        match value.trim().to_ascii_uppercase().as_str() {
            "TRACE" => Ok(UlogLevel::Trace),
            "DEBUG" => Ok(UlogLevel::Debug),
            "INFO" => Ok(UlogLevel::Info),
            "OK" => Ok(UlogLevel::Ok),
            "WARN" | "WARNING" => Ok(UlogLevel::Warn),
            "ERROR" | "ERR" => Ok(UlogLevel::Error),
            "FATAL" => Ok(UlogLevel::Fatal),
            other => Err(format!("unknown ULOG level '{other}'")),
        }
    }
}
