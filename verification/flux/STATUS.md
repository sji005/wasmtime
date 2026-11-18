# Execution checkpoint

The user authorized GitHub Actions on `sji005/wasmtime`, and then explicitly
authorized investigating/fixing Flux compatibility and continuing the original
proof. Work remains in branch `flux/fd-read-memory-isolation`, based on
`7c83a428028b44e1a73b40aa6a912d6700983624`. No upstream PR/comments are authorized
or allowed by AGENTS.md. Runtime behavior/control flow must remain original.

Completed evidence:

- M0 passed on Linux, including three checked smoke functions and three rejected
  well-typed negative variants. Both ordinary package checks and three boundary
  execution regressions passed. Fresh P1 ABI/types/linkers were captured.
- Original unmodified checker hit opaque-lifetime selection and unrelated
  bitflags ICEs. Full diagnostics are archived in `evidence/run-44240968739`.
- A narrow exact-source-slice adapter count experiment passed, including an
  excessive-return-count mutation; full-crate linkage remains open. See
  `evidence/run-44241913222`.
- The first separate checker patch fixes span selection only. It passed its
  positive/negative selection regressions and repeated strict M0 in
  [run 44243476970](https://github.com/sji005/wasmtime/actions/runs/44243476970).
  Candidate patch hash: `5672857a49a8614839459980138b720a916951d4c9f69abc6d34c2720b52abd7`.
  That candidate reaches actual production bodies: the original range validator's
  arithmetic checks, but no spatial postcondition exists yet. Unselected bodies
  are counted as trusted by Flux and remain explicitly unverified.

The remaining actual-body diagnostics with that first checker candidate are:

| Body | Result |
| --- | --- |
| validate_range | One body checked, strict overflow, two constraints; no spatial postcondition |
| validate_size_align / validate_size_align_mut | Missing range/slice refinement relationships |
| align_cells, GuestPtr::add, GuestPtr::iter, first_non_empty_iovec | Feasibility only; no spatial caller theorem |
| as_slice_mut / copy_from_slice | Ghost fold/unfold ICE on associated `Pointee::Pointer` tuple projection |
| GuestPtr::get_range / MemoryRanges::into_range_mut | Open refinement obligations |
| p1 fd_read | Desugaring error: unexpected opaque type |
| original Unix read adapter | Missing external FileExt result-count contract in full-crate context |

Next checker candidate adds Rust-driven associated-field normalization and
additional opaque-type diagnostic detail. It preserves the original driver,
uses explicit source-patch/binary receipts, and must pass selection, projection
and strict M0 negative gates. It also builds a narrow external spec crate for
`FileExt::read_at` specifically for std `File` and force-loads it into original
WASI compilation; the external metadata-loading experiment has its own positive
and rejected-negative gate. No local guest range checker is trusted.

Candidate commit `06a24eca33da9d49cd9a9e054cc5a2029d8440ec`,
[run 44244653512](https://github.com/sji005/wasmtime/actions/runs/44244653512),
passed integration but its checker build failed: this rustc's normalization API
requires `ty::Unnormalized::new(...)`. That API use is now corrected in the patch.
The next candidate also fails closed on an upstream fallback explicitly documented
as unsound because it erases refinements for unresolved associated type projections.
Sort-only normalization remains separate. Inspect the next run before advancing.
The compatibility driver cache is keyed by patch/build-script/pins hashes.

Run 44245526231 then built the checker successfully and passed selection tests,
but the associated-field regression still crashed. The normalization context
used the ADT's generic environment instead of the actual MIR owner's environment;
the patch now threads that real owner through structural fold/unfold analysis.
This normalization only handles unrefined Rust structural shapes. Refinement
normalization remains separate, with its unsafe erasing fallback disabled.

The next source candidate also adds specifications (no behavior changes) for
GuestPtr's associated Pointer field, construction, offset/cast, array formation
and base/length/accessor identities. These are not yet checked. The source guard
registers exact insertions, allows only a single balanced sig/refined_by/field
attribute per insertion, and rejects all runtime changes. Full-crate pointer
contract proof and mutations remain to run after checker compatibility.

Local paths useful for diagnosis (outside Git, within the shared workspace):

- `../.tooling/flux-source`: pinned Flux source with the patches applied locally.
- `../.tooling/fd-read-compatibility`: first candidate's complete original-body,
  selection and environment diagnostics, plus build receipt.
- `../.tooling/fd-read-original-glue`: full fresh expanded WASI source and P1
  wrapper from the original-source Linux run.

M1--M5 and the full conditional fd_read theorem remain incomplete. Next work
after checker compatibility is to annotate original pointer/range/metadata
bodies and establish caller contracts, with temporary mutations of any passing
proofs. Keep exact-fit/empty behavior, memory identity, typed widths/alignment,
error-after-effect ordering, async ownership and generated stores visible.
Shared memory, Windows and 32-bit hosts remain excluded pending separate checks.
