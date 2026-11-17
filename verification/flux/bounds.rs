// This imports the production implementation, rather than a proof-only copy.
#[path = "../../crates/wiggle/src/bounds.rs"]
mod bounds;

#[cfg(test)]
mod tests {
    use super::bounds::checked_range_end;

    #[test]
    fn exhaustive_small_ranges() {
        for memory_len in 0..=32 {
            for start in 0..=40 {
                for byte_len in 0..=40 {
                    let expected = if start + byte_len <= memory_len {
                        Some(start + byte_len)
                    } else {
                        None
                    };
                    assert_eq!(checked_range_end(start, byte_len, memory_len), expected);
                }
            }
        }
    }

    #[test]
    fn machine_word_boundaries() {
        let max = usize::MAX;
        assert_eq!(checked_range_end(max, 0, max), Some(max));
        assert_eq!(checked_range_end(max - 1, 1, max), Some(max));
        assert_eq!(checked_range_end(0, max, max), Some(max));
        assert_eq!(checked_range_end(max, 1, max), None);
        assert_eq!(checked_range_end(1, max, max), None);
        assert_eq!(checked_range_end(max, max, max), None);
        assert_eq!(checked_range_end(max, 0, max - 1), None);
        assert_eq!(checked_range_end(0, 0, 0), Some(0));
        assert_eq!(checked_range_end(1, 0, 0), None);
    }
}
