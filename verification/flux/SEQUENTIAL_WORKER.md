# Synchronous worker experiment

This separate experiment implements the user's revised sequential scope. It
does not change the frozen production sources or supersede their open theorem.

The original file worker allocates a zeroed Vec, calls the synchronous Unix
read adapter, truncates to the returned count, and returns the Vec. The async
wrapper schedules and awaits this closure. `sequential_worker.rs` performs those
buffer operations directly on the current thread, using a real OS read and
propagating errors. It does not manufacture bytes or return a dummy count.
The original StreamError/types::Error conversion is simplified to io::Error;
this is a transformed component experiment, not an exact extraction.

The proposed checked postcondition is `returned.len() <= requested_capacity`.
For this postcondition, Vec::truncate is important: it can shorten a Vec but
cannot grow it, even if given an excessive count. A length proof alone therefore
does not prove that the OS respected its destination or returned an honest count.
Both local bodies must check; neither is trusted. The existing external
FileExt::read_at contract bounds the successful count. As in TRUST.md, OS write
confinement on success and error, unrelated-allocation framing and Rust reference
validity remain explicit external assumptions, not a proved heap-effect theorem.

No scheduling, cancellation, stdin, guest-memory selection, metadata access,
copy-back or generated output store is proved here. Synchronous execution can
block the current thread and does not establish equivalence to the async path.
The native Windows execution branch uses seek_read only to test real file data
flow; it is outside the pinned Linux Flux claim.

On the existing pinned Linux environment, start from an unmodified Flux install
and unset FLUX_DRIVER and FLUX_COMPAT_RECEIPT. Run the baseline environment gate,
then compile_primitive_specs.py as in the existing workflow to populate
FD_READ_PRIMITIVE_MANIFEST, then:

```sh
python3 verification/flux/check_sequential_worker.py
```

The runner clears compatibility overrides again, checks ordinary Rust compilation
of both variants, requires both positive bodies checked, and requires a real
proof rejection of a variant returning an extra byte. Crashes and unsupported
constructs leave the result open. Removing overrides alone does not certify the
installed binary: retain baseline installer/environment provenance.

Runtime regression checks can be run separately with rustc --test on
sequential_worker.rs. They exercise actual reads, short reads, EOF, zero capacity
and errors. Execution tests do not establish the Flux postcondition.

Local preparation on November 18, 2026: Rust 1.98.0 on Windows successfully
typechecked the source and its test bodies using `--test --emit=metadata`.
Executing the tests is blocked because the MSVC linker link.exe is unavailable.
The Linux/unmodified-Flux probe has not run: no usable Flux or Python executable
is available in this local shell. No positive Flux result is claimed.

First Linux run: 44394247063, source 26f3aba. The unmodified checker passed its
positive/negative environment controls; all four real file-read regressions
passed. The worker postcondition failed with E0999, not a checker crash. The
pinned Flux Vec library has no from_elem/truncate length specifications.

The follow-up adds sequential_vec_specs.rs for those two standard Vec operations,
within the existing T-VEC assumption, after reviewing the pinned Rust source.
The worker implementation and OS read are unchanged. These external length
contracts are assumed, not proved Rust standard-library implementations.

Follow-up Linux run 44394963511, source 1297667: both local bodies checked with
unmodified Flux; the well-typed extra-byte variant failed refinement checking.
All four runtime tests passed. This establishes only the stated sequential
component contract under T-FILE and T-VEC. No scheduler or original hostcall
composition result follows from this run.
