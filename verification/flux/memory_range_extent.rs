//! Isolated spatial portion of MemoryRanges::into_range_mut.
//! The caller supplies a live, exclusive allocation and its logical extent.
//! The main proof constructs a raw slice descriptor. The separate constructor
//! probe checks whether Flux can recover the length of a Rust reference.

#[cfg(flux)]
extern crate flux_core;

use std::{ops::Range, ptr::NonNull};

/// # Safety
/// `base` must be valid for `len` initialized bytes of one live allocation,
/// with exclusive access and a length no greater than `isize::MAX`.
#[cfg_attr(flux, flux::sig(fn(base: NonNull<u8>[@b, b, @n], len: usize{len == n && len <= isize::MAX}, Range<usize>[@r]) -> Result<(NonNull<[u8]>[b, b + r.start, n - r.start], usize[r.end - r.start]), ()>[r.start <= r.end && r.end <= len]))]
pub unsafe fn memory_range_extent(
    base: NonNull<u8>,
    len: usize,
    range: Range<usize>,
) -> Result<(NonNull<[u8]>, usize), ()> {
    if range.start > range.end || range.end > len {
        return Err(());
    }
    let width = range.len();
    // SAFETY: the validated start is at most len, including an empty range at
    // the allocation end, and the width fits the remaining extent.
    let start = unsafe { base.add(range.start) };
    Ok((NonNull::slice_from_raw_parts(start, width), width))
}

/// # Safety
/// The caller must meet `memory_range_extent`'s allocation requirements.
#[cfg_attr(flux, flux::sig(fn(base: NonNull<u8>[@b, b, @n], len: usize{len == n && len <= isize::MAX}, Range<usize>[@r]) -> usize[r.end - r.start] requires r.start <= r.end && r.end <= len))]
pub unsafe fn validated_range_width(base: NonNull<u8>, len: usize, range: Range<usize>) -> usize {
    // SAFETY: the caller supplies the live allocation and the range is valid.
    let (_, width) = unsafe { memory_range_extent(base, len, range) }.expect("range was validated");
    width
}

/// # Safety
/// `start` must be valid for `width` initialized bytes, exclusively borrowed
/// for the returned lifetime, and `width` must be at most `isize::MAX`.
#[cfg(constructor_probe)]
#[cfg_attr(flux, flux::sig(fn(start: *mut[@p] u8, width: usize) -> &mut [u8][width] requires 0 < p.addr && p.base <= p.addr && width <= p.size && width <= isize::MAX))]
pub unsafe fn raw_slice_constructor<'a>(start: *mut u8, width: usize) -> &'a mut [u8] {
    // SAFETY: the caller supplies an initialized, exclusively borrowed region.
    unsafe { std::slice::from_raw_parts_mut(start, width) }
}
