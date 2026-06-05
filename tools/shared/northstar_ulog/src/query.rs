use crate::{UlogEvent, UlogLevel};

pub fn filter_by_level<'a>(events: &'a [UlogEvent], level: UlogLevel) -> Vec<&'a UlogEvent> {
    events.iter().filter(|event| event.level == level).collect()
}

pub fn filter_by_source<'a>(events: &'a [UlogEvent], source: &str) -> Vec<&'a UlogEvent> {
    events.iter().filter(|event| event.source.name.eq_ignore_ascii_case(source)).collect()
}

pub fn filter_by_event_id<'a>(events: &'a [UlogEvent], event_id: &str) -> Vec<&'a UlogEvent> {
    events.iter().filter(|event| event.event_id == event_id).collect()
}

pub fn search_text<'a>(events: &'a [UlogEvent], query: &str) -> Vec<&'a UlogEvent> {
    let q = query.to_ascii_lowercase();
    events.iter().filter(|event| {
        event.message.to_ascii_lowercase().contains(&q)
            || event.event_id.to_ascii_lowercase().contains(&q)
            || event.source.name.to_ascii_lowercase().contains(&q)
            || event.fields.to_string().to_ascii_lowercase().contains(&q)
    }).collect()
}
