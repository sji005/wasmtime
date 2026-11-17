//! Checks the exact production memory-policy implementation and its consumers.
#[cfg(flux)]
extern crate flux_core;

#[path = "../../crates/wiggle/src/bounds.rs"]
mod bounds;
#[path = "../../crates/wiggle/src/memory_policy.rs"]
mod memory_policy;
