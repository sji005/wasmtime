//! Isolated spatial portion of MemoryRanges::into_range_mut.
//! The caller supplies a live, exclusive allocation and its logical extent.
//! This experiment constructs a raw slice descriptor, not a Rust reference.

#[cfg(flux)]
extern crate flux_core;

use std::{ops::Range, ptr::NonNull};

/// # Safety
/// `base` must be valid for `len` initialized bytes of one live allocation,
/// with exclusive access and a length no greater than `isize::MAX`.
#[cfg_attr(flux, flux::sig(fn(base: NonNull<u8>[@b, b, @n], len: usize{len == n && len <= isize::MAX}, Range<usize>[@r]) -> Option<(NonNull<[u8]>[b, b + r.start, n - r.start], usize[r.end - r.start])>))]
pub unsafe fn memory_range_extent(
    base: NonNull<u8>,
    len: usize,
    range: Range<usize>,
) -> Option<(NonNull<[u8]>, usize)> {
    if range.start > range.end || range.end > len {
        return None;
    }
    let width = range.len();
    // SAFETY: the validated start is at most len, including an empty range at
    // the allocation end, and the width fits the remaining extent.
    let start = unsafe { base.add(range.start) };
    Some((NonNull::slice_from_raw_parts(start, width), width))
}
