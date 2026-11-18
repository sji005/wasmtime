# Execution checkpoint

The checked target is x86-64 Linux with WASI P1, which enables P2. The branch
`flux/fd-read-memory-isolation` starts at `7c83a428028b44e1a73b40aa6a912d6700983624`.
The source guard verifies that production differences consist of registered
Flux attributes. The `fd_read` theorem remains open.

| Evidence | Checked result | Scope |
| --- | --- | --- |
| [Baseline run 44240968739](https://github.com/sji005/wasmtime/actions/runs/44240968739) | Passed M0 with three positive functions and three rejected mutations. Ordinary builds, three boundary regressions and fresh P1 expansion passed. | Environment, original behavior on tested inputs, and generated source inspection |
| [Adapter run 44249865966](https://github.com/sji005/wasmtime/actions/runs/44249865966) | The original Unix adapter's success-count contract checked in full WASI. The temporary full-crate `Ok(usize::MAX)` mutation compiled as Rust and failed refinement checking. | One original function. Count bound relative to the external FileExt contract. Heap effects and caller composition remain open. |
| [Arithmetic run 44250912386](https://github.com/sji005/wasmtime/actions/runs/44250912386) | The original `validate_range` checked with strict overflow. Successful intervals start at the requested offset, are ordered, and have byte width at most `u32::MAX`. Shifting the start by one was rejected. | Original Wiggle crate. No memory length in that revision's postcondition. |
| [Slice bounds run 44252707563](https://github.com/sji005/wasmtime/actions/runs/44252707563) | The original `validate_range` also proved `end <= slice_len` for `Unshared` and `Shared`. The shift and removed bounds check mutations compiled as Rust and were rejected. The external `Range<usize>::clone` control checked both endpoints and rejected the wrong end. | One of 102 functions selected for Flux. The 101 excluded bodies remain unverified. The run's integration job passed. A later, independent generic tuple sort control failed. |
| [Integer layout and ABI run 44255286310](https://github.com/sji005/wasmtime/actions/runs/44255286310) | Original macro-expanded integer `guest_size` and `guest_align` matched the Rust size and alignment. Returning zero failed each contract. The generated P1 binding executed short read, truncated metadata, invalid result pointer and all-empty EOF cases. | One original WASI entry point tested on four concrete inputs. The typed access and end-to-end effect theorem remain open. |
| [Exact byte count run 44256865241](https://github.com/sji005/wasmtime/actions/runs/44256865241) | Successful `validate_range` results have width equal to the element count times the layout size for types with the checked size equality. The shifted offset, removed guard and halved width mutations were rejected. | Layout equality checked for the original integer implementations. Width and slice-backed bounds still need composition at the effects. |
| [Slice construction and nested async run 44258374102](https://github.com/sji005/wasmtime/actions/runs/44258374102) | Original `as_slice_mut` checked when built with the two slice-backed variants. The added byte at the end of the selected range failed. An index mutation inside a nested async block also failed. | The slice construction result uses the exact original body without the optional Wasmtime `Ranges` variant. The all-features probe still fails. The nested async control checks block contents, with the block's output using the default refinement. |
| [File and alias execution run 44259617175](https://github.com/sji005/wasmtime/actions/runs/44259617175) | The generated binding passed distinct direct file and worker copy-back fixtures. It also passed a case in which the result pointer aliases the payload. | Runtime execution. The environment job reached a downstream Rust metadata loader error after the original-body checks. |
| [Worker and range length run 44260731718](https://github.com/sji005/wasmtime/actions/runs/44260731718) | The `Range<usize>::len` specification checked and rejected an incorrect width. A small closure that owns a Vec reproduced the original worker's inference error. The controls using a mutable slice or a Vec outside a closure checked. | The original Wasmtime slice constructor still lacks the pointer provenance and return-length refinement. The standalone metadata loader error persisted. |

The immutable Action archives and their SHA-256 receipts are retained under
`evidence/`. The range bound for `Shared` concerns the validator's returned
interval only. Shared memory effects, atomics, raw copies and concurrency remain
separate obligations.

## Flux compatibility

The original pinned driver fails selection on synthetic opaque lifetime nodes
and unrelated macro expansions. The separate candidate fixes that selection,
normalizes Rust field shapes in their MIR owner's parameter environment, and
leaves unresolved type projections open when Rust-only normalization would
erase refinements. The candidate repeated the strict M0 positive and negative
checks and passed the selected function and unrefined associated field controls.
Each run retains the patch and binary digests.

The full crate pointer annotations remain experimental. Flux can lower the
associated field for structural analysis but cannot yet use its tuple refinement
in `GuestPtr<[T]>`. Generic constructor and accessor checks encounter unresolved
associated type projections. The tuple control separates direct tuple refinements
from this generic associated sort problem.

A free async function checks and rejects a wrong result. The native async trait,
explicit `impl Future + Send` trait and nested async examples reproduce the
synthetic opaque failure seen in the original `fd_read`. The signature
compatibility candidate applies rustc's mapping from a trait method's own
synthetic return projection to its original opaque type for structural
comparison. In [run 44254101472](https://github.com/sji005/wasmtime/actions/runs/44254101472)
that candidate reached output subtyping for the original `fd_read`. Flux then
tried to compare an implementation lifetime with the trait's `Self` type.
The next candidate uses the existing projection-bound checker for corresponding
trait/implementation opaques, including the `Future::Output` contract. Its
regression includes an implementation that satisfies its own weaker output
contract but violates its trait's contract. The native and explicit
`impl Future + Send` trait controls passed. The weakened implementation and
wrong body results were rejected. The original `fd_read` then reached a
`Future::Output` projection for tracing's nested async block. The new candidate
checks explicit local async block bodies before using their compiler-provided
default output type. A separate nested array access control requires checking
the block itself. That control passed and rejected the out-of-bounds index
mutation. The original `fd_read` now reaches its worker closure and has a
parameter inference failure on the `&mut buf` argument to the Unix adapter.
No preservation of an input-dependent result refinement across a nested
`await` has been shown.

For the worker, the candidate opens a strong place's existing existential
before introducing the callee's inference variables. It keeps the original
subtyping check and place blocking. The regression checks that a captured
buffer must still establish a callee's positive-length precondition.

## Open production obligations

- The generated linker uses `GuestMemory::Ranges`. Establish that
  `MemoryRanges::len` and raw slice formation refer to the same selected
  allocation and logical extent. Then prove the original range guard, byte
  footprint and returned slice against that extent. The original lookup chain
  and the source-level provenance argument are in [MEMORY_RANGES.md](MEMORY_RANGES.md).
- Relate pointer stride, typed widths, alignment and complete metadata reads.
  Check the original iterator and first non-empty iovec selection.
- Compose the direct file branch with the verified slice and the external file
  confinement assumption. Check worker and stdin copy-back, ownership through
  await and cancellation, and error ordering.
- Check the generated result store against its guest supplied pointer and its
  four-byte width. Account for reachable exits and aliasing.
- Keep shared memory effects, Windows and 32-bit targets outside the current
  theorem until each configuration's obligations are checked.
