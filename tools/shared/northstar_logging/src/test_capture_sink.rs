use crate::sink::UlogSink;
use northstar_ulog::UlogEvent;
use std::{error::Error, sync::{Arc, Mutex}};

#[derive(Clone, Debug, Default)]
pub struct TestCaptureSink {
    events: Arc<Mutex<Vec<UlogEvent>>>,
}

impl TestCaptureSink {
    pub fn new() -> Self { Self::default() }
    pub fn events(&self) -> Vec<UlogEvent> { self.events.lock().map(|events| events.clone()).unwrap_or_default() }
    pub fn contains_event_id(&self, event_id: &str) -> bool { self.events().iter().any(|event| event.event_id == event_id) }
}

impl UlogSink for TestCaptureSink {
    fn emit(&self, event: &UlogEvent) -> Result<(), Box<dyn Error>> {
        if let Ok(mut events) = self.events.lock() { events.push(event.clone()); }
        Ok(())
    }
}
