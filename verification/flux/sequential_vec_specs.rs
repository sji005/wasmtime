//! Length semantics within the already declared T-VEC standard-library boundary.
//! These are external assumptions, not checked implementations or checker patches.
//! Reviewed Rust revision: 1a2c4797ef2570bd76ca5dee34449169bc7dc457.
//! library/alloc/src/vec/mod.rs: from_elem creates n elements; truncate retains
//! the old length when the request is larger, and otherwise sets it to len.

#[flux_rs::extern_spec(std::vec)]
#[flux::sig(fn<T>(T, n: usize) -> Vec<T>[n])]
fn from_elem<T: Clone>(elem: T, n: usize) -> Vec<T>;

#[flux_rs::extern_spec]
impl<T, A: std::alloc::Allocator> Vec<T, A> {
    #[flux::sig(
        fn(self: &mut Vec<T, A>[@old], len: usize)
            ensures self: Vec<T, A>[if len < old { len } else { old }]
    )]
    fn truncate(&mut self, len: usize);
}
