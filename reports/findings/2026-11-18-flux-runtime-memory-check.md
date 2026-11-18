# Runtime Memory-Safety Verification

## Environment

- Date: 2026-11-18
- Platform: Linux 6.8.0-1070-azure, x86_64
- Wasmtime revision: `c6aabd092c8f1e0c523b42b6e0dbfb018f75d076`
- Review model identifier: not exposed by the session runtime

## Scope and result

Reviewed the Flux-related runtime memory changes associated with
`8a754da5138f9bc06006ffa80c69382ddb8c5a4b`, with the security review scoped
to the changed memory-related areas and their directly relevant callees.
No concrete memory-safety vulnerabilities were identified in that scope.
This is not a full audit of Wasmtime or a proof that it is memory-safe.

The Flux checks below completed successfully after trusting the Unix pagemap
bitflags macro. Without that exception, Flux reports a possible out-of-bounds
access in generated `all()` code, then hits an internal compiler error while
processing the same macro. This diagnostic is unresolved; it has not been
confirmed as either a real defect or a false positive. The focused memory
check reported 10 checked functions. Other functions were trusted or outside
the selected scope.

```text
mkdir -p /tmp/wasmtime-flux-log /tmp/wasmtime-flux-lean &&
cargo flux check --package wasmtime \
  --only-check 'glob:src/runtime/vm/memory.rs' \
  --Finclude-trusted 'glob:src/runtime/vm/sys/unix/pagemap.rs' \
  --Flog-dir /tmp/wasmtime-flux-log \
  --Flean-dir /tmp/wasmtime-flux-lean
```

The attempted check of `box_future` in `src/runtime.rs` remains unsupported:
Flux reports an unsupported unsize coercion from `Pin<Box<F>>` to a pinned
future trait object. This is a verifier limitation; the normal Rust build
accepts it. No source annotation was added to suppress this diagnostic.

## Validation

- `cargo check --package wasmtime --lib` — passed.
- Focused Flux check of `src/runtime/vm/memory.rs` — passed, 10 functions
  checked.
- Focused Flux checks of `src/runtime/memory.rs`, `src/runtime/vm/cow.rs`,
  and `src/runtime/vm/gc/gc_runtime.rs` — passed with the pagemap macro
  trusted.
- Flux checking `box_future` — blocked by the unsupported trait-object
  coercion; broad runtime checking also encounters the pagemap macro issue
  unless that generated code is trusted.

The initial review was static and did not include cross-platform testing;
subsequent focused runtime tests are documented below.

## Follow-up review

A separate defensive review covered the public linear-memory implementation
and directly relevant VM memory allocation, growth, and copy-on-write paths.
No concrete memory-safety findings were reported in those paths. This review
was static and bounded to the paths named above; it did not cover unrelated
Wasmtime subsystems or prove the absence of vulnerabilities.

## Additional bounds contracts

`Memory::read` and `Memory::write` now share checked range helpers whose Flux
specifications state that a successful result has exactly the requested
length. The helper validates `start` and `len` by subtraction before forming
the end offset, so the addition is only performed after the bounds prove it
cannot overflow. The write path still obtains and validates the whole range
before copying, preserving the all-or-nothing behavior on invalid bounds.

Focused Flux checks for `def:checked_memory_range`, `def:Memory::read`, and
`def:Memory::write` passed. The helper check processed 12 functions and solved
9 constraints; each public method check processed 11 functions. The
Unix-pagemap macro remained trusted out to avoid the known generated-code
checker failure.

The following targeted test passed:

```text
cargo test -p wasmtime --lib \
  runtime::memory::tests::memory_read_write_checked_ranges
```

It exercises reads and writes at the valid empty end range, overflowing
offsets, out-of-bounds ranges, and unchanged buffers/memory after failed
operations. `cargo fmt --all -- --check` and `git diff --check` also passed.

## Validated-slice contracts

The immutable and mutable slice constructors now take checked start/end
bounds and specify the exact length of the returned slice. The
`MemoryRanges::data_range_mut_if_in_bounds` contract likewise states that a
returned slice has length `end - start` whenever `start <= end`.

Focused Flux checks for `def:memory_range_slice`,
`def:checked_memory_range`, and
`def:MemoryRanges::data_range_mut_if_in_bounds` passed, with 12, 12, and 10
functions checked respectively. The first two checks solved 6 and 5
constraints. All 7 tests in `runtime::memory::tests` passed.

These refinements verify index and slice-length relationships. They do not
prove the validity, provenance, or aliasing requirements of raw pointers;
the raw-slice constructors remain trusted and depend on the surrounding
runtime invariants.
