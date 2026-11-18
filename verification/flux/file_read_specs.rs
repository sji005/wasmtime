//! Trusted primitive only: the std implementation for File, not a local wrapper.
//! The success count is encoded below. Confinement of writes to the supplied
//! mutable slice on success AND error, and framing of other allocations, remain
//! explicit external assumptions; Flux does not establish a heap-effect theorem.

use std::fs::File;
use std::io;
use std::ops::Range;
use std::os::unix::fs::FileExt;

// Rust 1a2c4797ef2570bd76ca5dee34449169bc7dc457:
// core/src/clone.rs, blob 61528873a38c7e87c50e4b481ea1e12f22090df6:
// these primitive Clone implementations return *self.
#[flux_rs::extern_spec]
#[flux_rs::assoc(fn cloned(old: int, new: int) -> bool { old == new })]
impl Clone for usize {
    #[flux::sig(fn(&usize[@n]) -> usize[n])]
    fn clone(&self) -> Self;
}

// core/src/ops/range.rs, blob d81279cb56be3cbc0ead7c4cd10db6ebbb60ff04:
// Range derives Clone field by field. Do not assume arbitrary Idx::clone is
// identity: retain the element implementation's own cloned relation.
#[flux_rs::extern_spec]
#[flux_rs::assoc(fn cloned(old: Self, new: Self) -> bool {
    <Idx as Clone>::cloned(old.start, new.start) && <Idx as Clone>::cloned(old.end, new.end)
})]
impl<Idx: Clone> Clone for Range<Idx> {
    #[flux::sig(fn(&Range<Idx>[@r]) -> Range<Idx>{out: <Idx as Clone>::cloned(r.start, out.start) && <Idx as Clone>::cloned(r.end, out.end)})]
    fn clone(&self) -> Self;
}

#[flux_rs::extern_spec]
impl FileExt for File {
    #[flux::sig(fn(&File, &mut [u8][@n], u64) -> Result<usize{v: v <= n}, io::Error>)]
    fn read_at(&self, buf: &mut [u8], offset: u64) -> io::Result<usize>;
}
