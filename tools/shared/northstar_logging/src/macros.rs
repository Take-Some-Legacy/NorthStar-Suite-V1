#[macro_export]
macro_rules! ulog_event {
    ($emitter:expr, $level:expr, $event_id:expr, $message:expr, $source_kind:expr, $source_name:expr, $run_id:expr $(, $key:ident = $value:expr )* $(,)?) => {{
        let mut event = northstar_ulog::UlogEvent::new($level, $event_id, $message, $source_kind, $source_name, $run_id);
        $( event = event.with_field(stringify!($key), serde_json::json!($value)); )*
        $emitter.emit(event)
    }};
}

#[macro_export]
macro_rules! ulog_info {
    ($emitter:expr, $event_id:expr, $message:expr, $source_name:expr, $run_id:expr $(, $key:ident = $value:expr )* $(,)?) => {
        $crate::ulog_event!($emitter, northstar_ulog::UlogLevel::Info, $event_id, $message, "tool", $source_name, $run_id $(, $key = $value )*)
    };
}

#[macro_export]
macro_rules! ulog_ok {
    ($emitter:expr, $event_id:expr, $message:expr, $source_name:expr, $run_id:expr $(, $key:ident = $value:expr )* $(,)?) => {
        $crate::ulog_event!($emitter, northstar_ulog::UlogLevel::Ok, $event_id, $message, "tool", $source_name, $run_id $(, $key = $value )*)
    };
}

#[macro_export]
macro_rules! ulog_warn {
    ($emitter:expr, $event_id:expr, $message:expr, $source_name:expr, $run_id:expr $(, $key:ident = $value:expr )* $(,)?) => {
        $crate::ulog_event!($emitter, northstar_ulog::UlogLevel::Warn, $event_id, $message, "tool", $source_name, $run_id $(, $key = $value )*)
    };
}

#[macro_export]
macro_rules! ulog_error {
    ($emitter:expr, $event_id:expr, $message:expr, $source_name:expr, $run_id:expr $(, $key:ident = $value:expr )* $(,)?) => {
        $crate::ulog_event!($emitter, northstar_ulog::UlogLevel::Error, $event_id, $message, "tool", $source_name, $run_id $(, $key = $value )*)
    };
}
