# Trust boundaries and open obligations

The full WASI crate check established the original Unix adapter's success-count
contract relative to the explicit `FileExt::read_at` contract. Heap effects and
caller composition remain open. The original Wiggle range arithmetic contract
also checked, including the selected slice length for slice-backed variants.
The generated linker's `MemoryRanges` bound remains open. The checked bodies
depend on the external primitive and standard-library assumptions below.

| ID | External assumption / machinery | Exact boundary and limitation |
| --- | --- | --- |
| T-LINMEM | Correct live selected linear-memory allocation, base/length, permissions and lifetime | The binding selects a Wasmtime Memory belonging to the caller's store. `MemoryRanges` retains Memory instance/index plus the StoreOpaque borrow; `.data()` and `.into_range_mut()` obtain base/current_length from that definition. Allocation origin correctness is assumed. Accessor forwarding, the consistency of `.len()` with that definition and guest offset validation still require checked contracts. The assumption never supplies guest-pointer validity. |
| T-FILE | Rust std / OS read primitive | The trusted external signature bounds the successful count by the supplied mutable slice length. Confinement to that slice on success and error and lack of effects on unrelated allocations are explicit external assumptions. The original Unix adapter forwards the same slice directly. Its checked postcondition encodes the count only. |
| T-RUST | Rust model, valid references and borrow/lifetime guarantees | Supplied slices describe valid initialized bytes for their stated lifetime. Rust references contribute provenance and exclusive/shared access guarantees. Numerical base/extent refinements are not a proof of those facts for an unsafe slice constructor. |
| T-CORE | Pinned Flux standard-library specifications | Reviewed slice len/as_ptr/as_mut_ptr/get/index and pointer add/copy semantics are pinned by Git blob IDs in `pins.json`; arithmetic Option/refinement specs are pinned with the same source revision. Slice indexing uses `start <= end <= len`; pointer specs retain base, address and remaining capacity. These specifications do not prove temporal safety or general heap framing. `from_raw_parts`, align_to, atomics, generic transparent types, conversions and async dependencies need further narrow specs/review in M1 onward. |
| T-RANGE | Standard `Range<usize>` endpoint cloning and length | `Range<Idx>` clones its two fields according to `Idx::cloned`. `usize::clone` returns its input. Exact size iteration uses `end - start` with zero for an empty or reversed range. The external specifications are pinned to the reviewed Rust source and have positive and incorrect-result controls. |
| T-VEC | Standard owned Vec behavior | Allocation, initialized elements, length/capacity and truncate semantics. Caller use of the read count, closure ownership, selected guest destination, and copy length remain obligations; no whole-worker wrapper is assumed safe. |
| T-STREAM | Owned host stream result | Stream/Bytes/Vec ownership and valid contents; no guest buffer is supplied to the primitive. P1's explicit returned-length check remains to be verified. A dynamic embedder stream's other effects must be declared at that external boundary; debug assertions do not prove its contract. |
| T-TASK | Trusted scheduling and result forwarding, authorized November 18, 2026 | Inline/worker dispatch, Tokio scheduling and join/poll/drop plumbing are assumed to preserve captured inputs and forward the exact callback result and its established contracts on normal completion. Ownership/lifetimes are respected; task machinery adds no guest effects beyond the callback. Cancellation need not stop a running blocking read. Callback preconditions, its body and owned capture discipline remain obligations. See SCHEDULING.md; this is an assumption, not a scheduler proof or an implemented Flux forwarding contract. |
| T-MACHINERY | Flux, Rust compiler model, solver and external specs | `pins.json` records the Flux revision, Rust toolchain, fixpoint and Z3. Each candidate records its patch and binary digests and repeats the strict M0 controls. Candidate support for explicit async blocks uses the default return refinement and requires checking the body. Result relationships across nested awaits and memory effects remain open. The upstream Cargo bootstrap remains non-hermetic. |

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
Scheduler internals and result forwarding are now assumed under T-TASK, as
authorized in [the scheduling scope decision](SCHEDULING.md). Callback capture
discipline, guest-memory validity across suspension and all guest accesses remain
open. No broad ignore/trust annotation discharges those obligations. The new
policy is documented; no production trusted annotation or new proof is added.

A future successful helper proof requires well-typed temporary mutations of its
original body, including removal of its bounds check and inflated access width or
offset. Its callers must establish that helper's preconditions. Runtime boundary
tests supplement that check and cannot close a universal proof obligation.

Excluded surfaces remain those in `PLAN.md`: other hostcalls, general Memory
read/write, compiler correctness, component ABI, descriptor rights, filesystem
confinement, file-content correctness and allocator verification. Shared memory
is a reachable fd_read variant explicitly excluded while its concurrency and
raw-copy/atomic obligations remain unresolved. These exclusions are not bugs.
