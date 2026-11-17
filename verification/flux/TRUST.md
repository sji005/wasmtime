# Trust ledger and coverage limits

The experiment distinguishes checked production code, checked models,
assumed external semantics, and outstanding proof obligations.
"0 trusted" in Flux's local function count does not eliminate external
specifications, compiler assumptions, or the need to connect a model to code.

| ID | Component / fact | Current status | Required evidence before a hostcall claim |
| --- | --- | --- | --- |
| V01 | Production checked_range_end in crates/wiggle/src/bounds.rs | Flux checked, strict overflow; four rejected mutations | Preserve source pin and import the real implementation. |
| V02 | Abstract memory effects and safe trace | Flux checked; 7 functions, 26 constraints, 5 rejected probes | Its owner/allocation labels are supplied model data; establish actual-memory binding and full operation coverage. |
| T01 | Flux b68c177, nightly compiler, fixpoint, Z3 | Trusted verification machinery, pinned as in README/install.sh | Retain exact revisions/digests and successful proof logs. Bootstrap is not hermetic. |
| T02 | flux_core Option and primitive/slice semantics | External standard-library specifications | Review specs at the pinned Flux revision. |
| T03 | flux_alloc Vec::new and Vec::push | External specifications; Rust/standard library trusted | Safe element typing supports policy preservation. Exact historical prefix/order also relies on Vec's actual append semantics; no independent trace-equivalence theorem is claimed. |
| B01 | Generated caller selects the calling instance's memory and context | Inspected, unproved | Tie proof witnesses to actual memory/context, not merely an integer label; preserve this relationship across reborrows. |
| B02 | Allocation base, provenance, extent and lifetime; unsafe guest slice bridges | Unproved | Prove or narrowly specify the actual pointer/reference bridge and framing of unrelated allocations. Offset arithmetic alone is insufficient. |
| B03 | Per-instance descriptor table, resource type, rights and file lifetime | Inspected, unproved | Verify initial provisioning and get_descriptor/resource-table translation, then lifecycle transitions and reuse. |
| B04 | Lazy Descriptors::new initialization | Outside initial conditional slice | Inventory initialization's reachable effects before covering the first hostcall on an uninitialized adapter. |
| B05 | FileExt::read_at -> std FileDesc::read_at -> libc::pread64 | Pinned std source inspected, unproved boundary | Add a narrow external contract: authorized live handle, bounded possible destination writes on all outcomes, success count, and framing. Kernel/libc implementation remains trusted. |
| B06 | Owned Vec allocation, initialized source, truncation and copy-back | Inspected, unproved | Separate host-scratch region policy; real source and destination bounds/lifetimes; prove nonempty raw-copy bridge or narrowly specify it. |
| B07 | Tokio spawn_blocking, Arc<File>, suspension and cancellation | Inspected, unproved | Running blocking tasks can outlive an abort request. Establish closure ownership and absence of escaping guest borrows. |
| B08 | Generated nread pointer/store and primitive u32 atomic bridge | Actual wrapper captured and checksummed; unproved | Prove the captured wrapper and primitive store: width, alignment, order, aliasing and traps. |
| B09 | Every real operation represented by the trace | Unproved | Resolve all selected branches/macros/dispatch/dependencies. A safe manually constructed trace can omit an unsafe real operation. |
| B10 | Filesystem and network confinement | Policy proposal only | Verify actual resolver/endpoint checks and dependencies under the selected configuration; audit extensions beyond WAVE. |

There are no new trusted adapters around OS calls in this package. T01–T03 are
assumptions used by the arithmetic/model experiment. B01–B10 are not silently
assumed to be established or reported as completed proofs.

The initial future fd_read theorem is conditional on a valid memory binding,
initialized authorized table, and a reviewed OS boundary contract. No syscall
site, entire hostcall, filesystem policy, or network policy is presently marked
verified in inventory.json. The existing runtime integration tests are evidence
about tested executions, not replacements for those proofs.

No claims are made about timing channels, availability, arbitrary host imports,
kernel correctness, shared memory, memory growth/reuse, or a verified compiler.
