use crate::sink::UlogSink;
use northstar_ulog::UlogEvent;
use std::{collections::VecDeque, error::Error, sync::{Arc, Mutex}};

#[derive(Clone, Debug)]
pub struct MemoryRingBufferSink {
    capacity: usize,
    events: Arc<Mutex<VecDeque<UlogEvent>>>,
}

impl MemoryRingBufferSink {
    pub fn new(capacity: usize) -> Self {
        Self { capacity: capacity.max(1), events: Arc::new(Mutex::new(VecDeque::new())) }
    }

    pub fn snapshot(&self) -> Vec<UlogEvent> {
        self.events.lock().map(|events| events.iter().cloned().collect()).unwrap_or_default()
    }
}

impl UlogSink for MemoryRingBufferSink {
    fn emit(&self, event: &UlogEvent) -> Result<(), Box<dyn Error>> {
        if let Ok(mut events) = self.events.lock() {
            while events.len() >= self.capacity { events.pop_front(); }
            events.push_back(event.clone());
        }
        Ok(())
    }
}
