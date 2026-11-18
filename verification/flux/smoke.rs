//! M0 toolchain probes only. These are not implementations of Wasmtime helpers.
#![allow(dead_code)]

#[cfg(flux)]
extern crate flux_core;

#[cfg_attr(flux, flux::sig(fn(x: u32, y: u32{y <= u32::MAX - x}) -> u32[x + y]))]
pub fn addition(x: u32, y: u32) -> u32 {
    x + y
}

#[cfg_attr(flux, flux::sig(fn(bytes: &[u8][@n], index: usize{index < n}) -> u8))]
pub fn slice_read(bytes: &[u8], index: usize) -> u8 {
    bytes[index]
}

#[cfg_attr(flux, flux::sig(fn(source: &[u8][1], destination: &mut [u8][1])))]
pub fn pointer_copy(source: &[u8], destination: &mut [u8]) {
    // SAFETY: the specification requires live one-byte slices. Rust borrows
    // supply allocation provenance/lifetimes; numerical bounds alone do not.
    unsafe { std::ptr::copy(source.as_ptr(), destination.as_mut_ptr(), 1) };
}
