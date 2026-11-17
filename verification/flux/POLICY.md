# WAVE policy correspondence, version 1

This selects the Wasmtime-compatible profile approved in the review plan.
It preserves the intended isolation properties while recording differences
from WAVE's literal predicates. No filesystem or network policy is proved yet.

Sources: WAVE [paper sections 3–4](https://cseweb.ucsd.edu/~dstefan/pubs/johnson:2023:wave.pdf),
[policy implementation](https://github.com/PLSysSec/wave/blob/ed984ed87571b985cab0afdb9a2960c7f9474b7c/src/tcb/verifier/spec.rs),
and [effects](https://github.com/PLSysSec/wave/blob/ed984ed87571b985cab0afdb9a2960c7f9474b7c/src/tcb/verifier/trace.rs).
The code and printed paper can differ; the distinctions below are intentional.

| Effect | Original WAVE predicate | Selected Wasmtime interpretation | Evidence / outstanding obligation |
| --- | --- | --- | --- |
| MemRead | Initialized linear memory; address at or above its base; strict upper endpoint; no address arithmetic wrap | Calling guest's live allocation; half-open byte range with exclusive end no larger than memory length; initialized readable bytes | Production offset arithmetic proved. Abstract label and trace checks proved in the model. Actual base/provenance/instance binding and primitive read bridge remain open. |
| MemWrite | Same spatial constraints | Calling guest's live writable allocation; half-open range and no wrap | Same limitations; OS writes and generated stores must be covered independently. |
| PathAccessAt | Correct root dirfd; relative path; no escaping prefix depth; safely resolved symlinks according to terminal-follow flag | Initially one exclusively provisioned root; verify Wasmtime's descriptor-based fast path and manual fallback | Policy specified only. Prefix-string checks and a model-only path witness are insufficient. |
| SockCreation | Implementation checks AF_INET and SOCK_STREAM or SOCK_DGRAM | Start with IPv4 outgoing TCP/UDP; constrain protocol selection at actual socket creation | Not implemented. The source predicate does not separately constrain a protocol field; any stronger protocol restriction must be documented. |
| NetAccess / NetConnect | Address/port belongs to the sandbox's unchanged allow-list | Concrete immutable endpoint allow-list; authorize actual point of use, including UDP alternate destinations | Not implemented. Arbitrary Wasmtime address-check callbacks are not automatically equivalent to this policy. |
| FdAccess | Accepted without a further restriction in the original predicate | Add a separate per-instance resource-table authority and lifetime invariant | Added obligation, not an existing WAVE descriptor check. Neither provisioning nor preservation is proved yet. |
| Shutdown | Accepted without a further restriction | Outside the initial file-only profile; later combine with live authorized socket ownership | No new shutdown restriction is claimed. |

## Exact-fit and zero-length ranges

For an allocation containing M bytes, use the mathematical interval
`[start, start + len)`, with `start <= M` and `len <= M - start`.
For any actually accessed byte index `i` with `0 <= i < len`, these conditions
imply `start + i < M`. For zero length there are no accessed bytes. An empty
range at M therefore needs no dereference. This explains the exact-fit choice;
it is not an assertion that WAVE's strict `<` predicate and ours accept the
same inputs. An empty range beyond M remains rejected by the range helper.

Absolute host pointer formation additionally needs an actual valid allocation,
base/provenance, lifetime, and nonwrapping address-space extent. The current
offset-arithmetic proof does not establish these facts. A raw integer owner or
memory label does not establish them either.

Wiggle's existing empty `copy_from_slice` path returns before destination
validation when the lengths agree. It has no copy effect. Do not impose the
range helper's acceptance rule as a functional specification of that whole API.

## Host scratch buffers are a separate extension

The worker branch of fd_read legitimately writes to an owned host Vec before
copying back. A guest-only memory predicate cannot authorize that operation.
The eventual extension must certify a particular owned allocation, its capacity,
initialized readable prefix, and lifetime. The effect model in this package
does not encode scratch allocations or prove worker copy-back.

Only safe effects belonging to one supplied abstract owner, allocation label,
and extent can enter a model trace. Copy effects currently describe two ranges
of that SAME guest allocation. They are not an OS copy or a guest/host transfer.

## Initial environment and context invariants

- Target x86-64 Linux GNU; WASIp1 ordinary files; p1 implies p2 internally.
- Fixed unshared guest memory; no guest threads or reentrant custom imports.
- Initially authorized, live descriptors in an initialized per-instance table.
- One exclusive root without adversarial external namespace mutation or special
  files such as `/proc/self/mem`; filesystem proof remains a later stage.
- Single-threaded guest execution does not remove host worker, scheduling,
  cancellation, or file-handle lifetime obligations.

WAVE's ctx_safe also includes representation-specific limits for its fixed
memory, arguments/environment, and unchanged network list. Do not transfer
those constants to Wasmtime without justification. Each future hostcall proof
must state and preserve the relevant Wasmtime context invariant instead.

## Feasibility result and gate

`effect_policy.rs` implements a trace whose Vec element type requires safe
ranges and matching owner/allocation/extent. Its constructors and append
operations are checked by Flux; its range validation imports the exact
production helper. The read/copy functions only record abstract footprints.
They execute no OS read or memory copy. Read versus write direction is checked
by the runtime tests; direction is not a refinement index in this prototype.

The [passing experiment](https://github.com/sji005/wasmtime/actions/runs/43991159857)
checked 7 functions, 0 locally trusted/ignored functions, and 26 constraints.
Five ordinary-Rust-valid probes were rejected: removed owner validation,
removed allocation validation, bypassed range validation, unconstrained trace
append, and appending an effect to a foreign trace.

Result: the basic refined-effect/trace representation works with the pinned
Flux. The concrete binding gate remains OPEN: prove non-forgeable association
with actual Wasmtime memory and the complete effectful operation before
claiming a production read/copy policy proof. A second required gate is proving
that every relevant real operation emits the modeled effect. See TRUST.md.
