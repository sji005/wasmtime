# Original fd_read memory-isolation investigation

Execution of [the supplied plan](PLAN.md), starting from clean Wasmtime
`7c83a428028b44e1a73b40aa6a912d6700983624`, on branch
`flux/fd-read-memory-isolation`. Production changes consist of Flux annotations.
The original Unix adapter's count contract, Wiggle's integer layout contracts,
and the original range validator's byte-count and slice bounds contracts passed.
Flux rejected well-typed mutations of each checked contract. The generated
entry uses `MemoryRanges`, whose selected-memory bound remains open along with
the end-to-end `fd_read` effect theorem. See [the checkpoint](STATUS.md).

M0 passed on the authorized GitHub Actions Linux runner. Three positive probe
functions checked (six constraints, zero local trusted/ignored bodies), all three
well-typed negative examples were rejected, both original packages compiled,
three original-body boundary regressions passed, and fresh ABI expansion was
captured. [The Linux run](https://github.com/sji005/wasmtime/actions/runs/44240968739)
and its digest-verified archives are retained under `evidence/run-44240968739`.

The pinned checker initially failed on span selection and generated bitflags.
A separate compatibility driver reaches the actual bodies and keeps unresolved
type projections open when resolving them would erase refinements. The checker
receipt records the base revision, patches, binary digest and pinned sysroot.
The unpatched checker remains available for comparison.

| Milestone | Status | Next evidence required |
| --- | --- | --- |
| M0: freeze/environment | Passed; 25 frozen inputs and 30 inspected edges | Preserve exact environment/evidence |
| M1: range/metadata | Arithmetic, exact integer width and slice-backed range bound checked. `MemoryRanges`, pointer refinements and typed access open | Check the selected allocation and original metadata reads |
| M2: direct file | Original adapter count checked in the full WASI crate. Slice and caller proof open | Compose original caller, range and slice contracts with external file confinement |
| M3: worker/stdin | Open | Check source/destination capacities, await ownership, cancellation and selected-memory stability |
| M4: generated ABI/errors | Fresh expansion inspected; proof open | Prove captured output store, selection, aliases and all error exits |
| M5: other configurations | Assessed as separate open obligations | Shared-memory concurrency/atomics/raw copies, Windows adapter and 32-bit arithmetic |

The investigation reused installer pins, diagnostic recognition and ABI capture
tooling from the old experiment `c6a59fc114302c2f6438893994138a0cbcfe2b12`.

## Frozen sources and coverage

`sources.json` pins the baseline Git source of reached dependencies, Cargo
configuration and WITX inputs. Hashing normalizes CRLF to LF so checkout
line-ending conversion cannot look like a runtime change. `check_sources.py`
compares both the baseline object and working tree and rejects changes anywhere
outside this verification directory, its workflow, its regression test and the
exact specification additions registered in `annotations.json`. The guard
reconstructs each permitted annotated file from the original Git blob and exact
registered insertion; all other edits fail. Baseline hashes never come from
annotated code.

`coverage.json` is the inspection ledger. Each row includes call edge,
configuration, pinned source, effect, pointer origin, offset/count, existing
check, primitive sink, status and trust dependency. A row's file hash is in
`sources.json`. These are obligations, not established dependency contracts or
a completeness certificate. Fresh generated code and compiler failures are
retained as evidence, and remain unproved.

Inspection observations to retain when writing contracts:

- The binding selects the caller's export named `memory`, uses
  `data_ranges_and_store_data_mut` for unshared memory, and constructs
  `GuestMemory::Ranges`. `Unshared` is a separate helper variant to check too.
- Metadata iteration uses checked `u32` element multiplication/addition and
  reads visited 8-byte iovec records in order. It stops at the first non-empty
  payload. All-empty input produces `(0, 0)`; it does not write every iovec.
- `validate_range` retains its original `offset + byte_len` expression. The
  two operands originate as `u32`, but strict-overflow verification on actual
  `usize` widths remains required. No replacement arithmetic was introduced.
- `MemoryRanges::into_range_mut` checks `start <= end <= full_length` before
  pointer addition. A returned sub-slice's length is distinct from the full
  linear-memory length. The `Ranges` typed write path has separate checked
  multiplication/addition before `align_cells`.
- The file branch evaluates `as_slice_mut` even when a worker is needed. That
  temporary borrow is dropped; the closure owns a host Vec. It truncates that
  Vec to the OS count and returns it before `get_range(0..n)` and copy-back.
- Stdin explicitly rejects an overlong returned Vec before copy-back. The
  stream implementation's debug assertion is not a release-mode guarantee.
- Empty `copy_from_slice` checks equal lengths and then succeeds before
  validating its unused destination pointer. `as_slice_mut`, including empty
  ranges, validates its range. Regression expectations preserve this difference.
- Metadata precedes descriptor rejection. Position overflow can happen after
  payload writes. An invalid generated result pointer may trap after payload
  effects. Fresh expansion confirms `match ret`: only `Ok(e)` performs the
  `Size=u32` store; `Err(e)` downcasts without a result store. That is inspected
  ordering evidence, not a checked function contract.

## Run the prepared M0 checkpoint

Use x86-64 Ubuntu 24.04 with rustup, Python 3, curl, unzip, git and a C linker.
Pins, target, features, reviewed primitive-spec Git blobs and proof flags are in
`pins.json`. This is a candidate toolchain; compatibility remains to be tested.

```sh
python3 verification/flux/check_sources.py
rustup toolchain install nightly-2026-10-22 --profile minimal \
  --component rustfmt --component rust-src --component rustc-dev --component llvm-tools
export RUSTUP_TOOLCHAIN=nightly-2026-10-22
bash verification/flux/install.sh
python3 verification/flux/check_environment.py --output-dir artifacts/fd-read/environment
cargo check --locked --target x86_64-unknown-linux-gnu -p wiggle --all-features
cargo check --locked --target x86_64-unknown-linux-gnu \
  -p wasmtime-wasi --no-default-features --features p1
cargo test --locked --target x86_64-unknown-linux-gnu \
  -p wiggle --all-features --test fd_read_memory
mkdir -p artifacts/fd-read/glue
cargo rustc --locked --target x86_64-unknown-linux-gnu \
  -p wasmtime-wasi --no-default-features --features p1 --lib \
  -- -Zunpretty=expanded > artifacts/fd-read/glue/wasi-expanded.rs
python3 verification/flux/capture_glue.py artifacts/fd-read/glue/wasi-expanded.rs \
  --output-dir artifacts/fd-read/glue
```

`.github/workflows/flux-fd-read.yml` runs these checks on the personal fork
only. Its independent environment and integration jobs separate checker
compatibility from ordinary compilation/tests. Original-body feasibility probes
and the adapter source-slice experiment do not establish a production safety proof.

The smoke runner requires exactly three checked, zero trusted, zero ignored
local probe bodies with strict overflow. It compiles all negative sources as
ordinary Rust before requiring an actual `E0999` refinement/overflow/bounds diagnostic.
Syntax errors, unsupported constructs, timeouts and missing tools fail the gate;
none count as bug evidence. Negative unsafe copies are compiled, never executed.
All four probe sources, commands, hashes, versions and full logs are retained.
The installer verifies solver archive hashes and reviewed external spec blobs;
the upstream wrapper installation is not hermetic. A mutable fixpoint URL must
fail closed if its pinned archive has changed.

The Wiggle regression test executes original Wiggle bodies and original
MemoryRanges accessors. It covers exact-fit/empty/end/beyond-end ranges, untouched
bytes on rejected copies, scalar width/alignment, multiplication and guest-offset
overflow, and full-region versus sub-slice length. The WASI regression executes
the generated P1 binding and checks exact-fit short reads, an all-empty EOF
read, truncated metadata and the effects preceding an invalid result pointer.
These tests cover concrete inputs. The proof and its remaining obligations are
tracked separately in [the checkpoint](STATUS.md).

## Configuration matrix

| Configuration | Status |
| --- | --- |
| Linux x86-64, p1+p2, unshared Ranges/direct file | Initial proof target; open |
| Linux x86-64, unshared Unshared helper variant | Original range and slice-return contracts checked without the optional `Ranges` variant |
| Linux x86-64, unshared worker and stdin | Open; no async or caller proof |
| Linux x86-64, shared memory | Reachable; excluded from initial claim; separate concurrency assessment required |
| Windows and 32-bit hosts | Excluded; no result inherited from Linux x86-64 |

The intended spatial condition uses mathematical `0 <= o <= L` and
`0 <= n <= L-o`, including exact fits and empty ranges at the end. A separately
named strict-endpoint comparison must never replace the production half-open
policy. Pointer validity/provenance/liveness cannot be inferred from those
numerical conditions alone. See [the trust boundaries](TRUST.md).
