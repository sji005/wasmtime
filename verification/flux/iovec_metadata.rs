//! Isolated WASI Preview 1 iovec offset and metadata range checks.

#[cfg(flux)]
extern crate flux_core;

use std::ops::Range;

const IOVEC_STRIDE: u32 = 8;
const FIELD_BYTES: u32 = 4;

// A direct match exposes the checked multiplication result to Flux.
#[cfg_attr(flux, flux::sig(fn(base: u32, index: u32) -> Option<u32[base + index * 8]>[base + index * 8 <= u32::MAX]))]
pub fn checked_iovec_offset(base: u32, index: u32) -> Option<u32> {
    let Some(displacement) = index.checked_mul(IOVEC_STRIDE) else {
        return None;
    };
    base.checked_add(displacement)
}

// Same arithmetic as the production GuestPtr::add specialized to an Iovec.
#[cfg(iterator_probe)]
#[cfg_attr(flux, flux::sig(fn(base: u32, index: u32) -> Option<u32[base + index * 8]>[base + index * 8 <= u32::MAX]))]
pub fn iovec_offset_through_and_then(base: u32, index: u32) -> Option<u32> {
    index
        .checked_mul(IOVEC_STRIDE)
        .and_then(|offset| base.checked_add(offset))
}

// The generated Iovec reader accesses two four-byte values at offsets 0 and 4.
// The second guest pointer is still a u32 before its range is checked.
#[cfg_attr(flux, flux::sig(fn(start: u32, len: usize) -> Option<(Range<usize>{r: r.start == start && r.end == start + 4 && r.end <= len}, Range<usize>{r: r.start == start + 4 && r.end == start + 8 && r.end <= len})>[start % 4 == 0 && start + 4 <= u32::MAX && start + 8 <= len]))]
pub fn iovec_metadata_ranges(start: u32, len: usize) -> Option<(Range<usize>, Range<usize>)> {
    let Some(second) = start.checked_add(FIELD_BYTES) else {
        return None;
    };
    let end = second as usize + FIELD_BYTES as usize;
    if start % FIELD_BYTES != 0 || end > len {
        return None;
    }
    Some((start as usize..second as usize, second as usize..end))
}
