//! Byte-range arithmetic shared by Wiggle and its standalone Flux harness.

/// Returns the exclusive end exactly when the entire range fits in memory.
///
/// Check the remaining space before adding, so even hostile offsets and
/// lengths cannot wrap the host's `usize` arithmetic. An empty range at the
/// end of memory is valid; an empty range beyond it is not.
#[cfg_attr(
    flux,
    flux::sig(fn(start: usize, byte_len: usize, memory_len: usize)
        -> Option<usize{end: end == start + byte_len && end <= memory_len}>
            [start + byte_len <= memory_len])
)]
pub(crate) fn checked_range_end(start: usize, byte_len: usize, memory_len: usize) -> Option<usize> {
    if start > memory_len {
        return None;
    }
    if byte_len > memory_len - start {
        return None;
    }
    Some(start + byte_len)
}
