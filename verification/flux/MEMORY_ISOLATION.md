# Production memory-isolation port

The policy now protects actual operations in `crates/wiggle/src/memory_policy.rs`.
`production_memory.rs` imports that production source directly for Flux; it
does not contain a second implementation. The earlier `effect_policy.rs` is a
separate abstract trace experiment, not evidence that the whole hostcall is safe.

## What the policy says

WAVE's memory portion of `trace_safe` requires valid linear memory, an address
at or above its base, a strict upper endpoint, and nonwrapping address
arithmetic. See the [pinned original policy](https://github.com/PLSysSec/wave/blob/ed984ed87571b985cab0afdb9a2960c7f9474b7c/src/tcb/verifier/spec.rs).

The production module records that literal spatial predicate as
`wave_memory_safe`. Its permits enforce the selected Wasmtime-compatible
`memory_safe` profile:

```
base > 0
0 <= memory_len; 0 <= count
base <= address
address + count <= base + memory_len <= usize::MAX
address <= address + count
```

The deliberate difference is `<=` at the exclusive endpoint: a buffer may fill
the allocation exactly, and an empty range at its end is allowed. Every byte
actually accessed is still strictly inside the allocation. This is a documented
adaptation, not a claim of identical acceptance to WAVE's strict `<` predicate.

## How it controls real memory

1. `MemoryPolicy::new` takes an actual exclusive Rust slice, capturing its
   pointer and length. Private fields and borrow lifetimes prevent public
   callers from supplying arbitrary pointer/owner labels or keeping a permit
   beyond its borrow.
2. `read` and `write` validate offsets with the proved production range helper.
   Their returned permits carry the region base, extent, exact access address,
   remaining capacity and requested count. Flux checks their invariants and
   pointer arithmetic with strict overflow checking.
3. `copy_from` and `copy_to` check the other slice's length and perform the real
   `std::ptr::copy`. Flux checks those calls against its pointer/copy specs.
   `copy_bytes` constructs and consumes a write permit for a real destination.
4. Unix `read_at` constructs a write permit for the actual destination slice
   and passes its bounded pointer/count to one explicitly trusted OS adapter.
   Its success count is proved no larger than the supplied capacity, conditional
   on that adapter's contract.

Production wiring with the `p1` feature:

- `filesystem/unix.rs::read_at_cursor_unspecified` calls the new policy read
  wrapper for both direct guest-buffer and worker-buffer reads.
- The `fd_read` worker and stdin copy-back paths use
  `GuestMemory::copy_from_bytes`; its unshared destination delegates to
  `memory_policy::copy_bytes`. The shared-memory fallback still uses the
  existing generic copy and is outside this proof profile.
- The public GuestMemory method, file-backend delegate and complete `fd_read`
  are compiled by CI but are not themselves checked end to end by Flux yet.

## What is trusted

Flux's standard-library specs describe slice pointers, pointer arithmetic and
`ptr::copy`. Rust's valid-reference and borrow rules supply allocation validity,
initialization, exclusivity and lifetime; Flux alone is not a temporal-memory
safety checker. The upstream unsafe bridge that creates the guest slice remains
an outstanding obligation.

The single locally trusted body, `os_read_at`, bridges a bounded raw pointer to
a slice and calls `FileExt::read_at`. Its Flux signature requires a nonnull
pointer with sufficient remaining capacity and bounds successful return counts.
We additionally assume the std/libc/kernel operation writes only within that
capacity on every outcome and frames other allocations. That write-footprint
and framing assumption is documented external semantics, not a proved Flux heap
effect theorem. File authorization is a separate unproved resource policy.

## Proof evidence and the role of tests

The [successful production run](https://github.com/sji005/wasmtime/actions/runs/44004096275)
checked revision `64bcdbe1ff60200bfe16d0872a3baeb4abd61d49`:
**11 functions checked, 38 constraints solved, one trusted function, zero
ignored functions**. This includes the shared production range helper.
Five ordinary-Rust-valid broken variants were rejected: bypassed range guards,
null root, foreign-allocation permit, oversized copy and oversized OS read.

The positive Flux result is universal over inputs satisfying the checked
functions' contracts, under the stated compiler/specification/OS assumptions.
Execution tests cannot establish that universal claim. They only check selected
behavior and integration. Negative mutations check that the verification setup
detects particular broken implementations; they are not the safety proof either.
CI therefore separates the `proofs` job from supplementary `integration` checks.

## Remaining work before a whole-fd_read claim

- Prove that generated dispatch selects the calling guest's actual memory and
  that the unsafe GuestMemory slice bridge preserves its allocation/lifetime.
- Verify iovec metadata loads, scalar operations and the final generated
  `nread` store, including errors and aliases.
- Compose direct, worker, stdin and error paths; establish ownership across
  suspension/cancellation and connect descriptor authorization/lifetime.
- Establish complete operation coverage. The detached safe-trace model does
  not prove that every real memory operation appears in a trace.

No full hostcall, all-Wasmtime memory-isolation, shared-memory concurrency,
memory-growth, Preview 2/3 or kernel-correctness theorem is claimed.
