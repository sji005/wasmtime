//! WAVE-derived memory isolation for operations on actual borrowed regions.
//!
//! A policy is created from a live mutable slice, not from caller-supplied
//! owner labels. Permits retain its real pointer provenance and borrow lifetime.
//! The half-open profile preserves Wasmtime's exact-fit and empty-buffer behavior.

#![cfg_attr(flux, flux::defs {
    // Literal spatial part of WAVE's published memory policy (strict endpoint).
    // Allocation validity/liveness is supplied by the originating Rust borrow.
    fn wave_memory_safe(base: int, memory_len: int, addr: int, count: int) -> bool {
        base > 0 && memory_len >= 0 && count >= 0 &&
        addr >= base && addr + count < base + memory_len &&
        base + memory_len <= usize::MAX && addr <= addr + count
    }

    // Approved Wasmtime profile: [addr, addr + count) may exactly fill a region.
    fn memory_safe(base: int, memory_len: int, addr: int, count: int) -> bool {
        base > 0 && memory_len >= 0 && count >= 0 &&
        addr >= base && addr + count <= base + memory_len &&
        base + memory_len <= usize::MAX && addr <= addr + count
    }
})]

use crate::bounds::checked_range_end;
use std::marker::PhantomData;

/// An exclusive borrow of the actual region authorized for an operation.
#[cfg_attr(flux, flux::refined_by(base: int, len: int))]
#[cfg_attr(flux, flux::invariant(base > 0 && 0 <= len && base + len <= usize::MAX))]
pub struct MemoryPolicy<'a> {
    #[cfg_attr(flux, flux::field(*mut[base, base, len] u8))]
    root: *mut u8,
    #[cfg_attr(flux, flux::field(usize[len]))]
    len: usize,
    borrow: PhantomData<&'a mut [u8]>,
}

#[cfg_attr(flux, flux::refined_by(base: int, memory_len: int, addr: int, remaining: int, count: int))]
#[cfg_attr(flux, flux::invariant(memory_safe(base, memory_len, addr, count)))]
#[cfg_attr(flux, flux::invariant(0 <= remaining && count <= remaining))]
#[cfg_attr(flux, flux::invariant(addr + remaining == base + memory_len))]
pub struct ReadAccess<'a> {
    #[cfg_attr(flux, flux::field(*const[base, addr, remaining] u8))]
    pointer: *const u8,
    #[cfg_attr(flux, flux::field(usize[count]))]
    count: usize,
    borrow: PhantomData<&'a [u8]>,
}

#[cfg_attr(flux, flux::refined_by(base: int, memory_len: int, addr: int, remaining: int, count: int))]
#[cfg_attr(flux, flux::invariant(memory_safe(base, memory_len, addr, count)))]
#[cfg_attr(flux, flux::invariant(0 <= remaining && count <= remaining))]
#[cfg_attr(flux, flux::invariant(addr + remaining == base + memory_len))]
pub struct WriteAccess<'a> {
    #[cfg_attr(flux, flux::field(*mut[base, addr, remaining] u8))]
    pointer: *mut u8,
    #[cfg_attr(flux, flux::field(usize[count]))]
    count: usize,
    borrow: PhantomData<&'a mut [u8]>,
}

impl<'a> MemoryPolicy<'a> {
    #[cfg_attr(flux, flux::sig(fn(&mut [u8][@n]) -> MemoryPolicy{p: p.len == n}))]
    pub fn new(memory: &'a mut [u8]) -> Self {
        let len = memory.len();
        let root = memory.as_mut_ptr();
        Self {
            root,
            len,
            borrow: PhantomData,
        }
    }

    #[cfg_attr(flux, flux::sig(fn(self: &MemoryPolicy[@p], start: usize, count: usize)
        -> Option<ReadAccess[p.base, p.len, p.base + start, p.len - start, count]>))]
    pub fn read(&self, start: usize, count: usize) -> Option<ReadAccess<'_>> {
        checked_range_end(start, count, self.len)?;
        // SAFETY: the validated range is inside the borrowed region. The permit
        // cannot outlive this shared reborrow of the exclusively held region.
        let pointer = unsafe { self.root.cast_const().add(start) };
        Some(ReadAccess {
            pointer,
            count,
            borrow: PhantomData,
        })
    }

    #[cfg_attr(flux, flux::sig(fn(self: &mut MemoryPolicy[@p], start: usize, count: usize)
        -> Option<WriteAccess[p.base, p.len, p.base + start, p.len - start, count]>))]
    pub fn write(&mut self, start: usize, count: usize) -> Option<WriteAccess<'_>> {
        checked_range_end(start, count, self.len)?;
        // SAFETY: the checked range and the exclusive reborrow are retained in
        // the permit. No raw pointer is exposed by the public API.
        let pointer = unsafe { self.root.add(start) };
        Some(WriteAccess {
            pointer,
            count,
            borrow: PhantomData,
        })
    }
}

impl ReadAccess<'_> {
    #[cfg_attr(flux, flux::sig(fn(self: ReadAccess[@a], &mut [u8]) -> bool))]
    pub fn copy_to(self, destination: &mut [u8]) -> bool {
        if destination.len() != self.count {
            return false;
        }
        // SAFETY: the source permit retains its live borrow; the destination
        // is a live writable slice of the same length. copy permits overlap.
        unsafe { std::ptr::copy(self.pointer, destination.as_mut_ptr(), self.count) };
        true
    }
}

impl WriteAccess<'_> {
    #[cfg_attr(flux, flux::sig(fn(self: WriteAccess[@a], &[u8]) -> bool))]
    pub fn copy_from(self, source: &[u8]) -> bool {
        if source.len() != self.count {
            return false;
        }
        // SAFETY: both regions are live and cover count bytes. The destination
        // permit is derived from this policy's real pointer, not a numeric tag.
        unsafe { std::ptr::copy(source.as_ptr(), self.pointer, self.count) };
        true
    }

    #[cfg(unix)]
    #[cfg_attr(flux, flux::sig(fn(self: WriteAccess[@a], &std::fs::File, u64)
        -> Result<usize{n: n <= a.count}, std::io::Error>))]
    pub fn read_at(self, file: &std::fs::File, offset: u64) -> std::io::Result<usize> {
        // SAFETY: the permit proves the destination footprint and holds its
        // exclusive borrow until this synchronous operation returns.
        unsafe { os_read_at(file, self.pointer, self.count, offset) }
    }
}

/// Actual byte copy used by WASI copy-back through GuestMemory::copy_from_bytes.
pub fn copy_bytes(destination: &mut [u8], source: &[u8]) -> bool {
    let count = destination.len();
    let mut policy = MemoryPolicy::new(destination);
    match policy.write(0, count) {
        Some(access) => access.copy_from(source),
        None => false,
    }
}

/// Actual Unix file-read wrapper used by Wasmtime's file backend with p1.
#[cfg(unix)]
#[cfg_attr(flux, flux::sig(fn(&std::fs::File, destination: &mut [u8][@n], u64)
    -> Result<usize{v: v <= n}, std::io::Error>))]
pub fn read_at(
    file: &std::fs::File,
    destination: &mut [u8],
    offset: u64,
) -> std::io::Result<usize> {
    let count = destination.len();
    let mut policy = MemoryPolicy::new(destination);
    match policy.write(0, count) {
        Some(access) => access.read_at(file, offset),
        None => Err(std::io::Error::from(std::io::ErrorKind::InvalidInput)),
    }
}

/// The only locally trusted body: the std/libc/kernel read boundary and its raw
/// slice bridge. Assume writes are confined to destination[0..count] on ALL
/// outcomes, successful n <= count, and unrelated allocations are unchanged.
/// Flux checks the callers' real pointer/range against this explicit contract.
#[cfg(unix)]
#[cfg_attr(flux, flux::trusted)]
#[cfg_attr(flux, flux::sig(fn(&std::fs::File, destination: *mut[@p] u8, count: usize, u64)
    -> Result<usize{n: n <= count}, std::io::Error>
    requires p.addr > 0 && p.addr >= p.base && 0 <= p.size && count <= p.size))]
unsafe fn os_read_at(
    file: &std::fs::File,
    destination: *mut u8,
    count: usize,
    offset: u64,
) -> std::io::Result<usize> {
    use std::os::unix::fs::FileExt;
    let destination = unsafe { std::slice::from_raw_parts_mut(destination, count) };
    file.read_at(destination, offset)
}
