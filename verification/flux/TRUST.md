# Trust boundaries and open obligations

The full WASI crate check established the original Unix adapter's success-count
contract relative to the explicit `FileExt::read_at` contract. Heap effects and
caller composition remain open. The original Wiggle range arithmetic contract
also checked, with the selected memory's bound still open. The checked bodies
depend on the external primitive and standard-library assumptions below.

| ID | External assumption / machinery | Exact boundary and limitation |
| --- | --- | --- |
| T-LINMEM | Correct live selected linear-memory allocation, base/length, permissions and lifetime | The binding selects a Wasmtime Memory belonging to the caller's store. `MemoryRanges` retains Memory instance/index plus the StoreOpaque borrow; `.data()` and `.into_range_mut()` obtain base/current_length from that definition. Allocation origin correctness is assumed. Accessor forwarding, the consistency of `.len()` with that definition and guest offset validation still require checked contracts. The assumption never supplies guest-pointer validity. |
| T-FILE | Rust std / OS read primitive | The checked external signature bounds the successful count by the supplied mutable slice length. Confinement to that slice on success and error and lack of effects on unrelated allocations are explicit external assumptions. The original Unix adapter forwards the same slice directly. Its checked postcondition encodes the count only. |
| T-RUST | Rust model, valid references and borrow/lifetime guarantees | Supplied slices describe valid initialized bytes for their stated lifetime. Rust references contribute provenance and exclusive/shared access guarantees. Numerical base/extent refinements are not a proof of those facts for an unsafe slice constructor. |
| T-CORE | Pinned Flux standard-library specifications | Reviewed slice len/as_ptr/as_mut_ptr/get/index and pointer add/copy semantics are pinned by Git blob IDs in `pins.json`; arithmetic Option/refinement specs are pinned with the same source revision. Slice indexing uses `start <= end <= len`; pointer specs retain base, address and remaining capacity. These specifications do not prove temporal safety or general heap framing. `from_raw_parts`, align_to, atomics, generic transparent types, conversions and async dependencies need further narrow specs/review in M1 onward. |
| T-VEC | Standard owned Vec behavior | Allocation, initialized elements, length/capacity and truncate semantics. Caller use of the read count, closure ownership, selected guest destination, and copy length remain obligations; no whole-worker wrapper is assumed safe. |
| T-STREAM | Owned host stream result | Stream/Bytes/Vec ownership and valid contents; no guest buffer is supplied to the primitive. P1's explicit returned-length check remains to be verified. A dynamic embedder stream's other effects must be declared at that external boundary; debug assertions do not prove its contract. |
| T-TASK | Tokio task/ownership semantics | Blocking closures and their return values satisfy Send + static. Aborting/dropping the handle need not stop running blocking work. The actual closure must be shown to capture only owned host buffers/file state; no general assumption that spawn_blocking makes guest borrows safe is permitted. |
| T-MACHINERY | Flux, Rust compiler model, solver and external specs | Flux revision/toolchain, fixpoint archive and Z3 archive pins are recorded in `pins.json`. Linux M0 acceptance/rejection passed. Full crates hit internal errors. The selection-only compatibility candidate has an explicit patch/binary receipt and separate regressions; it must repeat strict M0 acceptance/rejection. Installer archive verification does not establish checker soundness or hermetic Cargo wrapper installation. |

Local M0 probe functions: `addition`, `slice_read`, `pointer_copy`. No trusted or
ignored annotations exist in that harness. They are checker tests, not extracted
or reimplemented models of production functions. The successful case's three
contracts, the ordinary Rust compilation of all variants, and the specific
negative Flux diagnostics must all pass before using this candidate checker.

There are no explicitly trusted/ignored production annotations. Flux counts
functions excluded by an include selector as trusted; all such bodies remain
unverified here. The local empty explicit-annotation inventory never means all
dependencies have been verified. In
particular, `first_non_empty_iovec`, spatial validation, raw slice formation,
atomics, the direct caller, Vec worker, streams, cancellation, selected memory
identity across await and generated ABI stores are all open. Host-only descriptor
initialization/lookup/fuel/error code needs narrow no-guest-effect accounting.
No broad ignore/trust annotation discharges any of these obligations.

A future successful helper proof requires well-typed temporary mutations of its
original body, including removal of its bounds check and inflated access width or
offset. Its callers must establish that helper's preconditions. Runtime boundary
tests supplement that check and cannot close a universal proof obligation.

Excluded surfaces remain those in `PLAN.md`: other hostcalls, general Memory
read/write, compiler correctness, component ABI, descriptor rights, filesystem
confinement, file-content correctness and allocator verification. Shared memory
is a reachable fd_read variant explicitly excluded while its concurrency and
raw-copy/atomic obligations remain unresolved. These exclusions are not bugs.
