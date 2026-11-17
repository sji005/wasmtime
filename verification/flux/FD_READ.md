# fd_read: source map and proof obligations

Source baseline: Wasmtime `7f3dc0a6aed721b6f72a1cc5e6107a548d2bca17`.
Production files have not changed in the policy experiment. The machine-readable
[inventory](inventory.json) contains checked anchors, line numbers and normalized
source hashes. Rebuild with `python3 verification/flux/inventory.py`; verify
without changing it with `python3 verification/flux/inventory.py --check`.

This is an inspected partial effect graph. Its 46-export table is ABI accounting,
not 46 verified hostcalls or a complete transitive syscall graph.

```mermaid
flowchart TD
    A[Generated WASI binding selects caller memory] --> B[Read iovec metadata; first nonempty buffer]
    B --> C[Initialize or borrow per-instance descriptor table]
    C --> D{Descriptor kind}
    D -->|ordinary file| E[Get live file; validate guest destination]
    D -->|stdin| X[HostInputStream dispatch: deferred]
    D -->|other| Z[Badf]
    E --> F{Blocking permitted and slice borrowable?}
    F -->|yes| G[FileExt::read_at into guest slice]
    F -->|no| H[Owned zeroed Vec; inline or blocking worker]
    H --> I[FileExt::read_at into owned Vec]
    I --> J[Truncate to returned prefix; copy to checked guest range]
    G --> K[Checked position update; return count]
    J --> K
    K --> L[Generated nread store via GuestType u32]
```

## Guest and descriptor handling

The generated entry code in `crates/wiggle/generate/src/wasmtime.rs` obtains
the caller's `memory` export. The ordinary unshared branch constructs
`GuestMemory::Ranges`; shared memory is a separate branch outside the initial
profile. Proving the true allocation/instance binding is B01 in TRUST.md.

`first_non_empty_iovec` in `crates/wasi/src/p1.rs` traverses descriptors until it
finds one with nonzero `buf_len`, then returns that payload pointer. It checks
fuel and uses generated record-field loads. The record generator performs
field-offset pointer arithmetic; primitive guest loads use validated ranges,
alignment checks, and atomic/unsafe bridges. All those obligations remain open.

The array of descriptor metadata and the selected payload are different memory
regions and require separate checks. This path does not issue readv over every
guest entry. If all entries are empty, the selected range is `(0, 0)`; a zero
count is not automatically evidence that no OS operation occurs.

`transact()` may run `Descriptors::new` on first use. For the first conditional
ordinary-file slice, require an already initialized authorized descriptor table.
Lazy initialization is listed in the graph but its effects are unresolved. A
claim covering the first hostcall must discharge that additional branch.

Descriptor lookup then translates the guest fd into an instance-table entry,
borrows the component resource, and accesses its underlying file. A successful
lookup is not itself a proof of authorized provisioning or descriptor lifetime.

## Direct and worker branches

The file branch evaluates `memory.as_slice_mut(iov)?` while selecting between
direct and fallback execution, so destination validation occurs before the
ordinary-file worker read too.

- Direct: blocking is allowed and the guest memory can be borrowed. The backend
  reads directly into that guest slice.
- Fallback: drop any temporary guest slice, allocate a zero-filled Vec of the
  selected payload capacity, then call `File::run_blocking`. That helper either
  executes the closure immediately or spawns it; the closure owns the buffer.
  On success it truncates the buffer and the continuation copies the prefix
  back to the guest.

`Arc<File>` cloning and ownership are promising evidence for lifetime safety,
not a proof of it. `spawn_blocking` returns an abort-on-drop handle, but aborting
a handle is not sufficient to establish that an already running blocking task
has stopped. The future proof must establish that the worker owns everything
it may still use, and holds no escaping guest borrow.

`GuestMemory::copy_from_slice` validates length agreement and, for nonempty
copies, typed destination bounds/alignment before its raw `ptr::copy`. The
shared-memory branch has additional audit concerns and is excluded here.
The zero-length copy returns without destination validation and has no copy
effect. Capacity, initialization, raw-pointer provenance, and the scratch-memory
policy remain B02/B06 rather than checked facts.

## External boundary identified in pinned source

For compiler commit `1a2c4797ef2570bd76ca5dee34449169bc7dc457` on
`x86_64-unknown-linux-gnu`, the inspected chain is:

1. Wasmtime `filesystem/unix.rs::read_at_cursor_unspecified` calls
   `std::os::unix::fs::FileExt::read_at`.
2. The standard library's filesystem implementation delegates to `FileDesc`.
3. [`FileDesc::read_at`](https://github.com/rust-lang/rust/blob/1a2c4797ef2570bd76ca5dee34449169bc7dc457/library/std/src/sys/fd/unix.rs#L191)
   calls `libc::pread64(fd, destination, min(capacity, READ_LIMIT), offset)` and
   converts its result. The GNU/Linux import selects pread64 explicitly.

The C wrapper, deployed glibc and kernel implementation have not been verified
or pinned as executable artifacts. The repository's Cargo.lock libc version is
not a substitute for pinning the precompiled Rust standard library's internals.
This source trace identifies the boundary where a narrow contract belongs;
it does not constitute a proof of the syscall contract or its deployed binding.

Proposed contract requirements for that boundary:

- Descriptor is live and authorized under the context invariant.
- All possible destination writes fit the supplied writable allocation on
  every outcome, including errors. Use a conservative capacity footprint.
- A successful returned count lies between zero and the supplied capacity.
- Any source bytes subsequently read/copied are initialized.
- Other allocations and policy state are framed appropriately.

No contract asserting the entire fd_read hostcall safe has been introduced.

## Completion, errors, aliases and generated stores

After a read, `fd_read` checks position arithmetic and updates the stored
position. An overflow or later conversion error can occur after an OS effect
and a guest write. Do not model those errors as rollback.

The WASI result also requires a guest `nread` store. The inspected generator's
`Instruction::Store` emits `memory.write`, ultimately a u32 guest store.
Actual expanded fd_read glue still needs to be captured to close the graph.
Its result pointer may be invalid or overlap earlier data/metadata. Reason from
the actual evaluation order rather than assuming disjointness or no prior
effects when the final store traps.

The stdin branch dispatches through a HostInputStream and copies returned
bytes back after checking its returned length. Custom stream effects have not
been resolved. The current ordinary-file scope does not cover all fd_read
descriptor kinds.

## Checked model versus next concrete gate

The model imports the production range helper and proves that abstract memory
effects with mismatched labels or invalid ranges cannot enter its safe trace.
It records a file-read write footprint and a same-guest read/write copy pair.
It executes neither operation and supplies no scratch-buffer proof.

Next required gate: construct non-forgeable witnesses from the actual borrowed
Wasmtime memory, couple a narrow read/copy operation to its exact effect, and
prove that operation's real caller and its error paths preserve the selected
policy. All node statuses except the arithmetic helper remain unproved.
