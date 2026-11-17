# First Flux integration: Wiggle byte ranges

Imagine guest memory as a row of boxes. A guest asks the host to fill some
boxes. Before touching them, the host must check that every requested box
belongs to that row. This experiment connects Flux to that arithmetic check.

WASI Preview 1 is the older interface where guests pass memory addresses and
lengths directly. Preview 2 uses the Component Model and typed interfaces.
Preview 3 adds native asynchronous operations and streams; Wasmtime's support
is currently experimental. These are interface versions, not UI previews.

## Implementation

`crates/wiggle/src/bounds.rs` is the production implementation, also imported
directly by `verification/flux/bounds.rs`. Both `GuestMemory::validate_range`
and the mutable `GuestMemory::Ranges` typed-copy path call it.

The Flux contract states that a successful result is exactly `start + byte_len`
and no larger than `memory_len`. The `Option` index also states that the helper
accepts exactly the ranges whose mathematical sum fits. This rules out
an implementation that always refuses requests.

The implementation checks `start <= memory_len`, then
`byte_len <= memory_len - start`, before adding. Proofs use strict machine
integer overflow checking. No function is marked trusted and no raw pointer
dereference is allowed in this harness.

Existing checked element-size multiplication and integer conversions stay in
Wiggle. Host pointer addition now explicitly returns `PtrOverflow` on overflow;
the old general path used unchecked addition. Representable ranges outside
memory still return `PtrOutOfBounds`. Empty ranges at the end remain valid.

## Pinned experiment

| Component | Pin |
| --- | --- |
| Wasmtime starting revision | `7c83a428028b44e1a73b40aa6a912d6700983624` |
| Flux revision | `b68c177c5ace7cb3644fdeea140dc5d18669c6cc` |
| Flux compiler | `nightly-2026-10-22` |
| Local ordinary Rust check | Rust `1.98.0`, Wasmtime's minimum version |
| Linux runner | Ubuntu 24.04, x86-64 |
| Z3 | `5.3.3`, SHA-256 `d56f60b06f432f33de5810f7f1a384a339131f361e2d54d08ea83eea14326880` |
| Fixpoint release asset | `648710606`, SHA-256 `7f23b085b848d42ce91618c722cf867ca16e2b570d5d2427138ed80a99d80f9a` |

The fixpoint nightly download is mutable. The installer deliberately fails if
its contents change. Updating that pin requires reviewing the replacement.
The baseline uses Wasmtime's existing Cargo.lock with `--locked`. Flux uses
the pinned source and its upstream `cargo xtask install` workflow. The bootstrap
is not hermetic: upstream wrapper installation can resolve Cargo dependencies.
This standalone harness adds no Cargo dependencies and does not enable Flux
across the full Wasmtime workspace.

## Run on Linux

With rustup, Python 3, curl, unzip, git, and a C linker installed:

```sh
rustup toolchain install nightly-2026-10-22 --profile minimal --component rustfmt
rustup default nightly-2026-10-22
cargo check --locked -p wiggle --all-features
cargo test --locked -p wiggle --test bounds
rustc --edition=2024 --test verification/flux/bounds.rs -o /tmp/wiggle-bounds-tests
/tmp/wiggle-bounds-tests
bash verification/flux/install.sh
python3 verification/flux/check.py
```

The proof runner first checks the actual implementation. It then compiles and
checks four mutations: an off-by-one result, a missing start check, an incorrect
remaining-space check, and refusing valid requests. Each must produce a Flux
verification diagnostic; syntax errors or missing tools do not count.

The fork-only `.github/workflows/flux-bounds.yml` runs those checks on pushes to
`flux/**` branches. Its compiler compatibility check runs before Flux builds.

## Evidence and limits

Local results on Windows: Rust 1.98.0 compiled the shared source as a native
library and compiled its test harness to `wasm32-wasip1`. Node's Preview 1 WASI
runner passed both tests: all 55,473 small range combinations and nine
machine-word boundary cases. Formatting and whitespace checks passed.

SSH authentication works as `sji005`, and the branch is published on the fork.
The [successful Linux run](https://github.com/sji005/wasmtime/actions/runs/43987832550)
checked code revision `4bbde5de70612168f9e56c95e52de79873a466bb`:

- Formatting and both standalone helper tests passed on x86-64 Linux.
- `cargo check --locked -p wiggle --all-features` passed with Flux's compiler.
- All three guest-memory integration tests passed, including a typed copy into
  a real Wasmtime memory through the `Ranges` path.
- Flux checked the production helper: 1 function checked, 0 trusted, 0 ignored,
  and 9 constraints solved under strict overflow checking.
- All four mutations compiled as ordinary Rust and were rejected by Flux with
  refinement or arithmetic diagnostics (`E0999`).

The harness explicitly imports `flux_core` to load its standard-library
specifications. The cached checker was restored successfully in the passing
run. Documentation-only updates do not trigger another verification run.

This does not prove all of `fd_read`. The intended first proof is only byte-range
arithmetic. Remaining work includes element counts, alignment, guest-memory
identity, allocation lifetime, unsafe slice and copy bridges, iovec selection,
actual OS writes, short reads, errors, worker-buffer copy-back, and the generated
`nread` output store. Shared-memory concurrency, guest threads, and Preview 2/3
transfers need separate treatment.

The proof relies on Flux, its standard-library specifications, its compiler
model, fixpoint, and Z3. Importing the same source prevents a proof-only copy
from drifting, but does not prove its callers or establish memory ownership.

References: [Flux installation](https://flux-rs.github.io/flux/guide/install.html),
[Flux manifest settings](https://flux-rs.github.io/flux/reference/manifest.html),
[Wasmtime WASI versions](https://docs.wasmtime.dev/api/wasmtime_wasi/).
