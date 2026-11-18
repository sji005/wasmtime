# Original unshared MemoryRanges provenance

The generated Preview 1 linker constructs `GuestMemory::Ranges` for unshared
memory. The following is a source-level argument for the original
`MemoryRanges::into_range_mut` helper under the live-allocation assumption
in [TRUST.md](TRUST.md). Flux still needs to represent that assumption across
both lookups. This argument concerns one helper and its range, before any
file or stream operation uses the returned slice.

1. The linker selects the caller's exported `memory`. Its unshared branch
   passes that memory and the caller's store to
   `Memory::data_ranges_and_store_data_mut`. This accessor asserts that the
   memory belongs to the store, splits the store borrow and saves the original
   `Memory` handle alongside the opaque store borrow.
2. `MemoryRanges::data_range_mut` copies the same memory handle into the
   temporary receiver and reborrows the same store. The handle contains
   `instance` and `index`. The range argument is forwarded unchanged.
3. `MemoryRanges::len` reaches `Memory::internal_data_size`, which reads
   the logical length from
   `store[self.instance].memory(self.index).current_length()`. In
   `into_range_mut`, the base comes from the lookup with the same store
   and the two same handle fields. The only intervening operations compare
   the range endpoints with each other and with the length. The source of
   the two observations is `vm::Instance::memory`, which loads a
   `VMMemoryDefinition` containing the base and length. For this unshared
   memory and the exclusive store borrow, the definition is stable across
   those reads.
4. The early error rules out `start > end` and `end > len`. On the
   success path, with `L` the full logical length, the original code has
   `0 <= start <= end <= L`. The original `range.len()` therefore gives
   `end - start`. The live-allocation assumption supplies the pointer
   provenance, non-null base, valid extent and exclusive access for the
   store borrow. In particular, `VmPtr` stores a `NonZeroUsize` and
   `as_non_null` reconstructs the raw pointer using
   `with_exposed_provenance_mut`. The VM boundary supplies that provenance.
   Pointer addition stays within that allocation, including
   a possible one-past endpoint for a zero-width slice. The slice then has
   `end - start <= L - start` bytes. Its end is exactly `end`.

This argument distinguishes the full logical length returned by `len()`
from the width of the resulting slice. Exact fits and empty ranges at the end
follow from the non-strict upper bound. Reversed ranges and empty ranges beyond
the end return an error before pointer formation. The argument depends on
liveness and provenance from the VM boundary as well as the integer guard.

The Flux probe reaches the actual raw pointer addition and cannot prove its
precondition with the current refinements. To close that obligation, the
length and base must carry the same store, instance and memory selection
through the two lookups. The next contracts must retain the relation through
`VMMemoryDefinition::load`, its length accessor, and conversion of the
VM pointer into the raw byte pointer. Exact width alone, including a checked
specification for `Range<usize>::len`, leaves the raw slice constructor
obligation open. See [STATUS.md](STATUS.md) for the executable proof inventory.

## Zero-start subranges in copy-back

The original worker and stdin branches both call `get_range(0..returned_len)`.
For that call shape, the range is ordered and its length is the supplied
`returned_len`. If that length is at most the original iovec length, both
endpoint checks succeed. The original `GuestPtr::add(0)` computes
`0 * guest_size` and adds zero to the original offset. Both checked operations
succeed and preserve the base. The original `as_array` then replaces the
array length with `returned_len`.

The worker allocates a host Vec with the original iovec length. The external
file contract bounds its successful read count by that length. The closure
truncates and returns the host Vec. It captures the Vec and file position,
with the File supplied by the blocking task. The direct guest slice borrow
is dropped before the worker path awaits. The stdin path checks the returned
length explicitly before the subrange call. On x86-64, the original iovec
length is a `u32` and that upper bound also suffices for the conversion of
the returned count to `u32`.

This is a source-level argument for those two `unwrap` premises. Flux has
reached the original calls and still lacks the checked trait and container
contracts needed to establish those premises there. Copy-back also needs
the independent full guest destination and host source capacity proof.
