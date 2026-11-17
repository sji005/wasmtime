# Trust ledger and coverage limits

The experiment distinguishes checked production code, checked models,
assumed external semantics, and outstanding proof obligations.
"0 trusted" in Flux's local function count does not eliminate external
specifications, compiler assumptions, or the need to connect a model to code.

| ID | Component / fact | Current status | Required evidence before a hostcall claim |
| --- | --- | --- | --- |
| V01 | Production checked_range_end in crates/wiggle/src/bounds.rs | Flux checked, strict overflow; four rejected mutations | Preserve source pin and import the real implementation. |
| V02 | Abstract memory effects and safe trace | Flux checked; 7 functions, 26 constraints, 5 rejected probes | Its owner/allocation labels are supplied model data; establish actual-memory binding and full operation coverage. |
| V03 | Production borrowed-region permits, pointer arithmetic, byte-copy consumers and bounded read calls | Flux checked: 11 functions including V01, 38 constraints, 5 rejected mutations; one trusted OS adapter | Proof is relative to supplied valid Rust slices and external pointer/copy/read specs. Compose actual callers before a hostcall claim. |
| T01 | Flux b68c177, nightly compiler, fixpoint, Z3 | Trusted verification machinery, pinned as in README/install.sh | Retain exact revisions/digests and successful proof logs. Bootstrap is not hermetic. |
| T02 | flux_core Option, slice pointers, pointer arithmetic and ptr::copy semantics | External standard-library specifications; Rust valid-reference/borrow rules trusted | Review specs at the pinned Flux revision. Flux pointer checks alone do not prove temporal memory safety. |
| T03 | flux_alloc Vec::new and Vec::push | External specifications; Rust/standard library trusted | Safe element typing supports policy preservation. Exact historical prefix/order also relies on Vec's actual append semantics; no independent trace-equivalence theorem is claimed. |
| T04 | memory_policy::os_read_at | One explicitly trusted body: raw-slice bridge plus std/libc/kernel | Flux signature requires sufficient pointer capacity and bounds success count. Writes confined to that capacity on ALL outcomes and framing of other allocations are additional external semantic assumptions, not a checked heap-effect theorem. File authorization is separate. |
| B01 | Generated caller selects the calling instance's memory and context | Inspected, unproved | Tie proof witnesses to actual memory/context, not merely an integer label; preserve this relationship across reborrows. |
| B02 | Allocation base, provenance, extent and lifetime; unsafe guest slice bridges | Production policy captures real slice pointer/extent and retains Rust borrow lifetimes; upstream guest-slice bridge unproved | Establish that incoming slice represents the correct live guest allocation. Rust borrowing and trusted pointer specs support the checked module; they do not prove arbitrary unsafe callers. |
| B03 | Per-instance descriptor table, resource type, rights and file lifetime | Inspected, unproved | Verify initial provisioning and get_descriptor/resource-table translation, then lifecycle transitions and reuse. |
| B04 | Lazy Descriptors::new initialization | Outside initial conditional slice | Inventory initialization's reachable effects before covering the first hostcall on an uninitialized adapter. |
| B05 | FileExt::read_at -> std FileDesc::read_at -> libc::pread64 | T04 adapter implemented; production permit callers checked, OS implementation unproved | Kernel/libc/std behavior remains trusted. Prove outer file-backend delegation, descriptor authorization and caller composition. |
| B06 | Owned Vec allocation, initialized source, truncation and copy-back | Actual-slice copy_bytes/raw-copy consumer checked; outer GuestMemory method and task flow unproved | Compose scratch ownership, truncation and destination selection across worker execution. Shared generic-copy fallback excluded. |
| B07 | Tokio spawn_blocking, Arc<File>, suspension and cancellation | Inspected, unproved | Running blocking tasks can outlive an abort request. Establish closure ownership and absence of escaping guest borrows. |
| B08 | Generated nread pointer/store and primitive u32 atomic bridge | Actual wrapper captured and checksummed; unproved | Prove the captured wrapper and primitive store: width, alignment, order, aliasing and traps. |
| B09 | Every real operation represented by the trace | Unproved | Resolve all selected branches/macros/dispatch/dependencies. A safe manually constructed trace can omit an unsafe real operation. |
| B10 | Filesystem and network confinement | Policy proposal only | Verify actual resolver/endpoint checks and dependencies under the selected configuration; audit extensions beyond WAVE. |

T04 is the sole locally trusted function in the production memory harness.
The older arithmetic/model harnesses have zero locally trusted functions;
those counts must not be presented as the production port's count. T01–T04
remain assumptions, and incomplete B01–B10 obligations are not reported as proved.

The initial future fd_read theorem is conditional on a valid memory binding,
initialized authorized table, and the explicit OS boundary contract. Checked
module operations are marked relative to actual supplied slices; no entire
hostcall, filesystem policy or network policy is marked verified in inventory.json.
Runtime integration tests are evidence about tested executions, not replacements
for the universal conditional Flux proof.

No claims are made about timing channels, availability, arbitrary host imports,
kernel correctness, shared memory, memory growth/reuse, or a verified compiler.
