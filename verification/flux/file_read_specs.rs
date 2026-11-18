//! Trusted primitive only: the std implementation for File, not a local wrapper.
//! The success count is encoded below. Confinement of writes to the supplied
//! mutable slice on success AND error, and framing of other allocations, remain
//! explicit external assumptions; Flux does not establish a heap-effect theorem.

use std::fs::File;
use std::io;
use std::os::unix::fs::FileExt;

#[flux_rs::extern_spec]
impl FileExt for File {
    #[flux::sig(fn(&File, &mut [u8][@n], u64) -> Result<usize{v: v <= n}, io::Error>)]
    fn read_at(&self, buf: &mut [u8], offset: u64) -> io::Result<usize>;
}
