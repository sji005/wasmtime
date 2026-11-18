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

/// A model of the selected unshared VM definition after lookup. Its fields
/// share one extent, which must be established by whoever supplies the model.
#[cfg_attr(flux, flux::refined_by(addr: int, extent: int))]
#[cfg_attr(flux, flux::invariant(extent <= isize::MAX))]
pub struct MemoryDefinitionSnapshot {
    #[cfg_attr(flux, flux::field(NonNull<u8>[addr, addr, extent]))]
    base: NonNull<u8>,
    #[cfg_attr(flux, flux::field(usize[extent]))]
    current_length: usize,
}

/// # Safety
/// The selected snapshot must describe a live, exclusive allocation as in
/// `memory_range_extent`.
#[cfg_attr(flux, flux::sig(fn(&MemoryDefinitionSnapshot[@m], Range<usize>[@r]) -> usize[r.end - r.start] requires r.start <= r.end && r.end <= m.extent))]
pub unsafe fn range_width_from_snapshot(
    definition: &MemoryDefinitionSnapshot,
    range: Range<usize>,
) -> usize {
    let len = definition.current_length;
    let base = definition.base;
    // SAFETY: the selected allocation and valid range are supplied by the caller.
    unsafe { validated_range_width(base, len, range) }
}

/// Probe the pointer reconstruction expression used by `VmPtr::as_non_null`.
/// The inputs describe the address and extent of the selected allocation.
#[cfg(provenance_probe)]
#[cfg_attr(flux, flux::sig(fn(addr: usize{addr > 0}, extent: usize) -> *mut[addr, addr, extent] u8))]
pub fn reconstruct_vm_base(addr: usize, _extent: usize) -> *mut u8 {
    core::ptr::with_exposed_provenance_mut(addr)
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
