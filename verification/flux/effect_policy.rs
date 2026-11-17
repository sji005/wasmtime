//! Feasibility model for WAVE-style memory-effect preservation.
//!
//! Owner and allocation labels here are mathematical inputs, not authenticated
//! Wasmtime memory identities. This experiment does not perform a syscall or
//! prove the hostcall-to-allocation binding. See POLICY.md and TRUST.md.
#![allow(dead_code)]

#[cfg(flux)]
extern crate flux_alloc;
#[cfg(flux)]
extern crate flux_core;

#[path = "../../crates/wiggle/src/bounds.rs"]
mod bounds;

#[cfg_attr(flux, flux::refined_by(owner: int, memory: int, limit: int))]
pub struct ModelPolicy {
    #[cfg_attr(flux, flux::field(usize[owner]))]
    owner: usize,
    #[cfg_attr(flux, flux::field(usize[memory]))]
    memory: usize,
    #[cfg_attr(flux, flux::field(usize[limit]))]
    limit: usize,
}

#[cfg_attr(
    flux,
    flux::refined_by(owner: int, memory: int, limit: int, start: int, len: int)
)]
#[cfg_attr(flux, flux::invariant(0 <= start && start <= limit))]
#[cfg_attr(flux, flux::invariant(0 <= len && len <= limit - start))]
pub struct SafeMemoryEffect {
    #[cfg_attr(flux, flux::field(usize[owner]))]
    owner: usize,
    #[cfg_attr(flux, flux::field(usize[memory]))]
    memory: usize,
    #[cfg_attr(flux, flux::field(usize[limit]))]
    limit: usize,
    #[cfg_attr(flux, flux::field(usize[start]))]
    start: usize,
    #[cfg_attr(flux, flux::field(usize[len]))]
    len: usize,
    write: bool,
}

impl ModelPolicy {
    #[cfg_attr(flux, flux::sig(fn(owner: usize, memory: usize, limit: usize)
        -> ModelPolicy[owner, memory, limit]))]
    pub fn new(owner: usize, memory: usize, limit: usize) -> Self {
        Self {
            owner,
            memory,
            limit,
        }
    }

    /// Validate an abstract effect against this policy. Real allocation-label
    /// provenance remains a separate obligation at the Wasmtime boundary.
    #[cfg_attr(flux, flux::sig(fn(&ModelPolicy[@p], usize, usize, start: usize,
        len: usize, bool) -> Option<SafeMemoryEffect[p.owner, p.memory, p.limit, start, len]>))]
    pub fn validate(
        &self,
        owner: usize,
        memory: usize,
        start: usize,
        len: usize,
        write: bool,
    ) -> Option<SafeMemoryEffect> {
        if owner != self.owner || memory != self.memory {
            return None;
        }
        match bounds::checked_range_end(start, len, self.limit) {
            Some(_) => Some(SafeMemoryEffect {
                owner,
                memory,
                limit: self.limit,
                start,
                len,
                write,
            }),
            None => None,
        }
    }
}

/// Every stored element is a safe effect for the same policy. Vec::push is
/// specified by flux_alloc; its implementation is part of the trust ledger.
#[cfg_attr(flux, flux::refined_by(owner: int, memory: int, limit: int))]
pub struct SafeTrace {
    #[cfg_attr(flux, flux::field(ModelPolicy[owner, memory, limit]))]
    policy: ModelPolicy,
    #[cfg_attr(flux, flux::field(Vec<SafeMemoryEffect{e:
        e.owner == owner && e.memory == memory && e.limit == limit}>))]
    events: Vec<SafeMemoryEffect>,
}

impl SafeTrace {
    #[cfg_attr(flux, flux::sig(fn(ModelPolicy[@p]) -> SafeTrace[p.owner, p.memory, p.limit]))]
    pub fn new(policy: ModelPolicy) -> Self {
        Self {
            policy,
            events: Vec::new(),
        }
    }

    #[cfg_attr(flux, flux::sig(fn(&mut SafeTrace[@p], SafeMemoryEffect{e:
        e.owner == p.owner && e.memory == p.memory && e.limit == p.limit})))]
    pub fn append(&mut self, effect: SafeMemoryEffect) {
        self.events.push(effect);
    }

    /// A read from a file may WRITE the entire supplied destination capacity.
    /// Record that conservative footprint, independently of the returned count
    /// or success/error outcome. This models an effect; it does not do I/O.
    pub fn record_file_read(
        &mut self,
        owner: usize,
        memory: usize,
        destination: usize,
        capacity: usize,
    ) -> bool {
        match self
            .policy
            .validate(owner, memory, destination, capacity, true)
        {
            Some(effect) => {
                self.append(effect);
                true
            }
            None => false,
        }
    }

    /// This first model handles a copy between TWO ranges of the SAME guest
    /// memory. Owned worker-buffer copy-back requires a separate region policy.
    pub fn record_guest_copy(
        &mut self,
        owner: usize,
        memory: usize,
        source: usize,
        destination: usize,
        len: usize,
    ) -> bool {
        let read = match self.policy.validate(owner, memory, source, len, false) {
            Some(effect) => effect,
            None => return false,
        };
        let write = match self.policy.validate(owner, memory, destination, len, true) {
            Some(effect) => effect,
            None => return false,
        };
        self.append(read);
        self.append(write);
        true
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn read_and_copy_append_safe_effects_in_order() {
        let mut trace = SafeTrace::new(ModelPolicy::new(7, 11, 32));
        assert!(trace.record_file_read(7, 11, 24, 8));
        assert!(trace.record_guest_copy(7, 11, 24, 0, 8));
        assert_eq!(trace.events.len(), 3);
        assert!(trace.events[0].write);
        assert!(!trace.events[1].write);
        assert!(trace.events[2].write);
        assert_eq!(trace.events[0].start, 24);
        assert_eq!(trace.events[1].start, 24);
        assert_eq!(trace.events[2].start, 0);
        for event in &trace.events {
            assert_eq!((event.owner, event.memory, event.limit), (7, 11, 32));
            assert!(event.start <= 32 && event.len <= 32 - event.start);
        }
    }

    #[test]
    fn invalid_requests_leave_history_unchanged() {
        let mut trace = SafeTrace::new(ModelPolicy::new(7, 11, 32));
        assert!(trace.record_file_read(7, 11, 0, 1));
        for (owner, memory, start, len) in [
            (8, 11, 0, 1),
            (7, 12, 0, 1),
            (7, 11, 32, 1),
            (7, 11, usize::MAX, 1),
            (7, 11, 1, usize::MAX),
        ] {
            assert!(!trace.record_file_read(owner, memory, start, len));
            assert_eq!(trace.events.len(), 1);
        }
        assert!(!trace.record_guest_copy(7, 11, 0, 31, 2));
        assert_eq!(trace.events.len(), 1);
        assert_eq!(trace.events[0].start, 0);
    }

    #[test]
    fn empty_exact_fit_effect_is_allowed() {
        let mut trace = SafeTrace::new(ModelPolicy::new(7, 11, 0));
        assert!(trace.record_file_read(7, 11, 0, 0));
        assert!(trace.record_guest_copy(7, 11, 0, 0, 0));
        assert_eq!(trace.events.len(), 3);
    }
}
