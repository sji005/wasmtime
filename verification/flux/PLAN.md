# Plan: Flux verification of fd_read memory isolation

Status: design only. No new Flux proof, bug finding or runtime change is claimed.

Branch: `flux/memory-effects-plan`, based on clean `main` at
`7c83a428028b44e1a73b40aa6a912d6700983624`.
Reference experiment: `origin/flux/wiggle-bounds` at
`c6a59fc114302c2f6438893994138a0cbcfe2b12`.

## 1. Sole objective and scope

Verify memory isolation for the existing WASI Preview 1 `fd_read` execution path,
from its generated guest ABI entry through metadata reads, payload writes and
the generated result store. Check the path compositionally: verify function
bodies against contracts and check that callers establish their callees'
requirements. Shared helpers are included only where fd_read reaches them.

Start with the direct, unshared-memory file path on x86-64 Linux. Then cover
the unshared worker/copy-back and stdin paths, errors and generated ABI stores.
The complete claim is conditional on the trusted boundaries below and explicitly
limited to the checked target/features/memory variants. Shared memory is a
reachable fd_read configuration: track it as an exclusion initially, then assess
it as a separate obligation before any claim covering all fd_read configurations.

Excluded: other WASI calls (including fd_pread), general Memory::read/write
verification, Wasm load/store or bulk-instruction verification, Cranelift/Winch/
Pulley correctness, component ABI, filesystem confinement, descriptor rights,
file-content correctness and general allocator verification. Code outside fd_read
is inspected only to establish a dependency contract or justify an assumption.
Do not add independent verification projects for these excluded surfaces.

## 2. Preserve the code being investigated

The goal is to find out whether existing code is safe, not to construct a new
safe implementation first. Keep runtime behavior and control flow unchanged.
Add Flux annotations, external primitive specifications and proof harnesses;
do not add bounds helpers, permits, wrappers, replacement arithmetic, extra
runtime checks, changed call sites or the old branch's copy_from_bytes path.

Freeze production source hashes. Review baseline-to-annotated diffs to ensure
only specifications were added. Do not silently replace an unsupported construct
with a simpler implementation. An extracted/reimplemented model is exploratory
evidence until connected to the actual body, not proof of the original function.

Classify proof failures as an implementation defect, specification error,
missing justified assumption or checker limitation. A failed proof alone does
not establish a bug. Preserve original source, diagnostic, target/features and
an executable reproducer where possible before proposing repairs. Fixes belong
in separate subsequent changes with before/after evidence.

## 3. The memory-isolation contract and trusted boundaries

For every guest-memory effect reached by fd_read, require that its full byte
footprint belongs to the selected linear memory, with no arithmetic overflow.
For offset `o`, byte count `n`, and logical memory length `L`, the spatial target is:

```text
0 <= o <= L
0 <= n <= L - o
end = mathematical(o + n)
```

These are specification conditions, not instructions to rewrite existing checks.
Prove the existing operations and branches establish them before each actual
effect. For typed metadata/result accesses, count includes the complete access
width; check conversions, element-size multiplication and alignment too.

The supplied host-address predicate is:

```text
valid_linmem(base)
&& addr >= base
&& addr + count < base + memlen
&& base <= base + memlen
&& addr <= addr + count
```

For byte lengths, the production endpoint is `addr + count <= base + memlen`:
Wasm permits exact-fit accesses in the half-open interval. Keep the strict `<`
policy separately named if needed for comparison. Integer refinements use
mathematical values; enable strict machine-overflow checking and preserve actual
target widths. Do not derive Rust pointer validity from numerical bounds alone.
An empty range at the end fits; an empty range beyond it does not fit this range
predicate. Check each original API's actual empty/early-return behavior separately:
an operation with no byte effect need not validate an unused pointer unless its
specified ABI/error behavior requires it.

Trust boundaries:

* **valid_linmem:** assume Wasmtime supplies the correct live linear-memory base
  and corresponding logical length with appropriate access permissions and
  lifetime. Allocator/origin correctness is not part of this proof. Name the
  existing boundary that supplies this pair; preserve the relationship through
  the path. Never extend this assumption to guest offsets/counts or assume the
  safety of an internal range check we intend to verify.
* **File-read primitive:** trust the standard-library/OS read contract: writes
  stay within the supplied mutable slice on success and error, and a successful
  byte count does not exceed its length. Other allocations are not modified by
  that buffer write. A return-count bound alone does not establish confinement.
  Check the local adapter/caller against this contract; do not verify libc/kernel.
* **Host buffer/stream primitives:** record valid slice/Vec and owned-buffer
  semantics, and the contracts actually needed for blocking/stream results.
  Do not trust a broad wrapper that hides a guest-memory access under analysis.
* **Verification machinery:** pinned Flux, Rust model, standard-library specs,
  fixpoint and Z3; Rust lifetime/borrow guarantees. List every trusted or ignored
  body. Unsupported heap framing or async reasoning remains an explicit gap,
  never an implicit checked result.

## 4. Actual fd_read dependency graph

```text
Generated wasi_snapshot_preview1 fd_read entry
  -> construct GuestMemory from the selected Wasmtime memory
  -> p1.rs::fd_read
       -> first_non_empty_iovec
            -> GuestPtr iteration + GuestMemory::read (iovec metadata)
       -> File / direct:
            GuestMemory::as_slice_mut
              -> validate_range<u8>
              -> Unshared slice indexing OR MemoryRanges::data_range_mut
            sys::read_at_cursor_unspecified(file, guest_slice, position)
       -> File / worker fallback:
            owned host Vec -> blocking file read -> truncate
            -> GuestPtr::get_range -> GuestMemory::copy_from_slice
       -> Stdin:
            stream read -> explicit result-length check
            -> GuestPtr::get_range -> GuestMemory::copy_from_slice
       -> other descriptor/error branches
  -> generated nread store / ABI return and error handling
```

This baseline selects the first non-empty iovec; it does not read payload into
every iovec. Verify the metadata iteration and the selected payload range as
implemented. For the all-empty case the selector returns `GuestPtr::new((0,0))`.
Record generated error/store ordering from fresh expansion rather than assuming it.

| Source | fd_read-specific role and obligation |
| --- | --- |
| `crates/wiggle/generate/src/wasmtime.rs` | Binding setup: currently uses Memory::data_ranges_and_store_data_mut for unshared memory or SharedMemory::data for shared memory. Capture actual generated expansion and selected memory. |
| Wiggle-generated Preview 1 ABI glue | Decode arguments, dispatch fd_read, encode results; check actual output pointer/store width, metadata and error paths. |
| `crates/wasi/src/p1.rs`: fd_read, first_non_empty_iovec | Select/iterate metadata, choose direct/worker/stdin branch, retain counts and memory identity, handle errors and await. |
| `crates/wiggle/src/lib.rs`: read, as_slice_mut, copy_from_slice and reached validation routines | Check original bounds/conversions, source and destination capacity, slice formation and raw copies. |
| `crates/wiggle/src/guest_type.rs` and generated iovec types | Actual scalar/record reads and u32 result store: widths, offsets, alignment and primitive contracts. |
| `crates/wasmtime/src/runtime/memory.rs`: reached MemoryRanges methods and binding accessor | data/data_range_mut/into_range_mut and setup as actually reached; check range selection and pointer/slice derivation relative to valid_linmem. Do not include unrelated Memory::read/write. |
| `crates/wasi/src/filesystem/unix.rs`: read_at_cursor_unspecified | Existing local adapter delegates to FileExt::read_at. Verify bounded-slice forwarding relative to the trusted read contract. |
| Reached blocking/stream delegation | Prove or document result buffer ownership/count and guest-pointer stability across suspension; exclude unrelated filesystem functionality. |

Maintain a small coverage table: call edge, configuration, source hash, effect
kind, pointer origin, offset/count expression, original check, primitive sink,
proof status and trust dependency. Include generated code and dispatch. Searches
assist discovery but do not establish completeness. A checked helper alone does
not prove any unchecked caller or branch.

## 5. Ordered proof milestones

### M0 — Freeze and reproduce the proof environment

Record the baseline revision, Linux target, feature set and generated ABI inputs.
Use the old candidate Flux `b68c177c5ace7cb3644fdeea140dc5d18669c6cc` with
`nightly-2026-10-22` and its solver/specification pins as a starting point; validate
compatibility rather than relying on historical logs. Use an available Linux
runner or WSL2 environment; native Windows checker support is not assumed.
Run minimal positive/negative arithmetic, slice and pointer examples first.

Gate: reproducible checker output with strict overflow, reviewed primitive specs,
and well-typed bad examples rejected for refinement/overflow reasons. Syntax
errors, unsupported features, timeouts and missing tools are not proof failures.

### M1 — Prove existing range and metadata access dependencies

Annotate the existing Wiggle validation and the MemoryRanges accessors reached
by fd_read. Check both Unshared and Ranges behavior for the chosen configuration.
Check original arithmetic, conversions, slice formation and actual guest-type
reads. Verify GuestPtr iteration and first_non_empty_iovec, including element
stride, array bounds, all-empty/first-nonempty cases and fuel/error exits.
Keep full-region length distinct from a returned sub-slice's length.

Gate: every included body has a checked contract or classified open failure;
no new bounds helper and no assumed bounds postcondition for an unchecked body.
Boundary regressions cover end-of-memory, exact-fit, zero length, overflowing
offset/count/multiplication and malformed iovec metadata. Record target-width
limits: a 64-bit proof does not establish 32-bit correctness.

### M2 — Compose the direct unshared file path

Prove the existing chain:

```text
trusted memory base/length
  -> existing guest range validation
  -> bounded guest mutable slice
  -> existing read adapter
  -> trusted file-read contract
```

Check fd_read's actual arguments and byte-count conversions. Prove that the
local read adapter forwards the same slice without enlarging it. Treat file
position bookkeeping only as needed for control flow and errors. Writes may
precede a later error (for example position overflow); do not assume errors imply
no memory modification. Check that all effects before error remain confined.

Gate: claim only “direct unshared fd_read payload path is spatially confined,
relative to listed assumptions.” Metadata and generated output-store obligations
remain visible until completed. Do not call this a complete fd_read proof.

### M3 — Verify worker copy-back and stdin paths

Check the original worker flow: host Vec allocation, closure ownership, read
count, truncation, returned length, GuestPtr::get_range and copy_from_slice.
Prove both source capacity and guest destination footprint. Inspect what guest
access is dropped before await and what is reacquired at copy-back. Account for
cancellation and work that can outlive an abort without leaking guest pointers.

For stdin, check the existing explicit read.len() bound and subsequent subrange
and copy. Preserve actual ordering and early exits. Track errors after partial
effects; do not add revalidation or change the worker flow to make it verify.

Gate: original branch contracts compose, or unsupported async/ownership reasoning
and failing access obligations are explicitly open. A proof of an inner copy
does not discharge caller buffer-selection or lifetime obligations.

### M4 — Close generated ABI and error-path coverage

Expand the actual fd_read binding for the pinned inputs/features and preserve
source provenance/hash. Check the generated nread store (u32 width, pointer,
alignment and validation), success/error ordering and traps. Connect the actual
entrypoint's memory selection and GuestMemory construction to the valid_linmem
assumption without assuming validity of the guest-provided output address.

Handle metadata/payload/output aliasing according to actual sequential behavior;
do not assume guest pointers are disjoint. Include descriptor rejection, fuel
failure, empty/short reads, malformed metadata, out-of-bounds output, OS/stream
errors and relevant unwind/cancellation exits. Host-only bookkeeping can use
narrow contracts where it performs no guest access; inventory any dependency
that can reach guest memory rather than broadly ignoring it.

Gate: all guest-memory effects and reachable branches in the selected unshared
Linux configuration are accounted for. Only then claim conditional fd_read
memory isolation for that configuration. No correctness claim about file rights,
contents or the OS is implied.

### M5 — Decide coverage of remaining fd_read configurations

Shared memory takes different Wiggle paths and may involve raw copies/atomic
metadata access. Record these reachable paths from the start. Assess bounds,
alignment and Rust concurrency semantics separately before extending the theorem.
Keep shared memory explicitly excluded while unresolved. Similarly, Windows and
32-bit hosts require checking their actual adapters and arithmetic; they inherit
no proof from x86-64 Linux. These extensions remain limited to fd_read.

Gate: publish the configuration matrix with checked/trusted/open/excluded status.
Never generalize a direct-path or unshared proof to every fd_read execution.

## 6. Evidence, reuse and reporting

Reuse the old branch's checker bootstrap/pins, actual-source harness approach,
strict-overflow settings, diagnostic recognition and temporary mutation strategy.
Use FD_READ.md and TRUST.md as inspection aids, not verified facts about this
baseline. Consult its bounds contract for the target property, but do not port
the helper, permits, altered P1 calls, Unix adapter changes, abstract safe traces,
general policy inventory or unrelated verification scope.

For each run retain source/tool revisions, target/features, generated-code hashes,
flags, checked/trusted/ignored bodies, solver result, assumptions and failures.
Ensure a harness checks original bodies rather than duplicated proof-only code.
Review narrow dependency specifications; do not assume the guest bounds property
at an intermediate call just to get its caller to pass.

For passing proofs, mutate temporary copies to remove an existing bounds check,
inflate a copy/store width or change an offset. Require ordinary Rust compilation
and an appropriate Flux rejection. Mutations outside a trusted precondition do
not test the conditional theorem. Keep checker limitations and Rust borrow-check
rejections distinct. Runtime tests/reproducers supplement universal checks.

Run ordinary compilation/regressions for the chosen fd_read feature set as
annotations are introduced. Example initial check:

```sh
cargo check --locked -p wiggle --all-features
```

Add exact proof/integration commands when implemented; no new harness is present
in this planning-only change. No execution of a checker is claimed here.

Deliver small changes: environment and frozen graph; existing range/metadata
annotations; direct path composition; worker/stdin composition; generated ABI
closure; optional remaining fd_read configurations. Confirmed bugs and their
fixes are separate artifacts. Follow repository policy: upstream PR creation is
manual, and contributions require human review.

## References

* [Core Wasm memory instructions](https://webassembly.github.io/spec/core/exec/instructions.html#memory-instructions)
* [Flux specifications and trusted bodies](https://flux-rs.github.io/flux/guide/specifications.html)
* [Flux source](https://github.com/flux-rs/flux)
* Local historical inspection: `git show origin/flux/wiggle-bounds:verification/flux/FD_READ.md`
  and `git show origin/flux/wiggle-bounds:verification/flux/TRUST.md`.
