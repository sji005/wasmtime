# Trusted scheduling boundary

Scope decision: November 18, 2026. The user explicitly authorizes treating task
scheduling as trusted to simplify this experiment. This supersedes the earlier
requirement to discharge scheduler internals. Future accepted proof runs should
use the unmodified pinned checker; historical candidate-checker results retain
their original labels and are not converted into baseline results.

## What T-TASK assumes

For the fd_read worker, the boundary covers inline-versus-worker dispatch in
filesystem::File::run_blocking, File::spawn_blocking, runtime::spawn_blocking,
Tokio task scheduling, and AbortOnDropJoinHandle polling/drop plumbing. General
poll/wake/suspend/resume machinery is trusted wherever reached. This is an
assumption about scheduling and forwarding, not about every async function.

- The supplied FnOnce computation is invoked at most once, with the captured
  values and file handle forwarded intact. Normal completion returning a value
  corresponds to one completed invocation; no result is fabricated.
- On normal completion the exact callback result is forwarded, including its
  Result success/error variant and any proved relationships to captured inputs.
  A verified length bound therefore remains available after completion. This
  is the intended semantic contract; expressing it in baseline Flux is still an
  implementation obligation, not an established proof result.
- Task machinery respects Rust ownership, lifetimes and Send/static bounds,
  and adds no guest-memory effects beyond those of the supplied computation.
- No termination, fairness or response-time property is claimed. Panic, join
  failure and cancellation need not produce a successful result. Dropping or
  aborting the handle does not guarantee that a running blocking read stops.

The callback's preconditions must be established before dispatch. Its body must
be verified separately; T-TASK does not grant an arbitrary closure a safe-memory
contract. In particular, retain the obligation that this worker captures owned
host buffer/file state and no guest access that can outlive its valid borrow.
Continuing work after cancellation must remain within those owned resources.

## What remains to prove

Allocation/read/truncate arithmetic and returned length belong to the worker
proof. OS read count and write confinement use the separately documented T-FILE
boundary. Guest-memory selection, pointer validity, metadata reads, bounds,
copy-back, original error ordering and generated result stores remain checked
code obligations. Stream production/read semantics are not classified as mere
scheduling. Guest-memory identity and validity at copy-back must still be shown.

A proposed whole-hostcall statement is consequently conditional on T-TASK plus
the other declared external assumptions. Scheduling is classified trusted, never
reported as verified. This decision establishes no new hostcall proof.

## Checker consequences

Omitting scheduling-body proofs can reduce the async obligations. It cannot
guarantee that baseline Flux can parse/lower the surrounding trait, Future or
associated types, nor that it can express result forwarding across await.
Unsupported constructs or crashes remain tool limitations, not successful
verification. Do not respond by trusting fd_read or its worker body wholesale.

The separate sequential_worker.rs experiment remains useful for checking the
synchronous body without task machinery. It is a transformed component, not a
proof that the original async caller meets its contracts.
