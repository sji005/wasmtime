#!/usr/bin/env python3
"""Account for the P1 ABI and snapshot inspected fd_read source boundaries.

This is a drift detector and a review index, not a call-graph completeness proof.
"""

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TARGET = ROOT / "verification/flux/inventory.json"
WITX = "crates/wasi/witx/p1/wasi_snapshot_preview1.witx"
P1 = "crates/wasi/src/p1.rs"
PROVED_BOUNDS_SHA256 = "4692ba10d0c4187968e69045f494e025e5f8c97eb2007b9d4e37edac9b4976e0"
MEMORY_POLICY = "crates/wiggle/src/memory_policy.rs"
PROVED_MEMORY_SHA256 = "b83545ee77aa6734d9abe91bc0eda5f26c53259abd9f02abd9621ae4b897eddf"
GLUE = "verification/flux/evidence/fd-read/fd-read-glue.rs"
GLUE_METADATA = "verification/flux/evidence/fd-read/evidence.json"


def source(path):
    return (ROOT / path).read_text(encoding="utf-8")


def location(path, anchor):
    text = source(path)
    if text.count(anchor) != 1:
        raise ValueError(f"expected one source anchor: {path}: {anchor}")
    return {"path": path, "line": text[:text.index(anchor)].count("\n") + 1, "anchor": anchor}


def build():
    import re

    glue_evidence = json.loads(source(GLUE_METADATA))
    if hashlib.sha256(source(GLUE).encode()).hexdigest() != glue_evidence["wrapper_sha256"]:
        raise ValueError("Saved expanded wrapper checksum mismatch")

    witx = source(WITX)
    exports = list(re.finditer(r'\(@interface\s+func\s+\(export "([^"]+)"\)', witx))
    assert len(exports) == 46 and len({m[1] for m in exports}) == 46
    unsupported = {"fd_allocate", "fd_fdstat_set_rights", "proc_raise"}
    rows = []
    for match in exports:
        name = match[1]
        implementation = location(P1, f"fn {name}(")
        scope = "ordinary_file_branches_first" if name == "fd_read" else "deferred"
        note = "No resolved syscall graph or hostcall proof yet."
        if name.startswith("sock_"):
            scope, note = "excluded_p1_socket_stub", "Error stub; working networking is in P2/P3."
        elif name in unsupported:
            scope, note = "excluded_unsupported", "Unsupported operation in this revision."
        rows.append({
            "export": name,
            "witx": {"path": WITX, "line": witx[:match.start()].count("\n") + 1},
            "implementation": implementation,
            "initial_scope": scope,
            "proof_status": "unproved_hostcall",
            "effect_graph_status": "inspected_partial" if name == "fd_read" else "unresolved",
            "note": note,
        })

    def node(identifier, path, anchor, branch, effects, obligation, status="unproved"):
        return {"id": identifier, "source": location(path, anchor), "branch": branch,
                "effects": effects, "obligation": obligation, "proof_status": status}

    memory_status = ("checked_relative_to_supplied_valid_slice"
                     if hashlib.sha256(source(MEMORY_POLICY).encode()).hexdigest() == PROVED_MEMORY_SHA256
                     else "unproved_changed_since_evidence")
    nodes = [
        node("caller_memory", "crates/wiggle/generate/src/wasmtime.rs", 'let export = caller.get_export("memory");', "all",
             [], "Bind the actual memory and context to the calling instance; reject missing export."),
        node("iovec_selection", P1, "fn first_non_empty_iovec(", "all",
             ["MemRead(iovec descriptors)"], "Validate each descriptor actually traversed and select the first nonempty entry; do not assume readv over all entries."),
        node("generated_iovec_record", "crates/wiggle/generate/src/types/record.rs", "fn read(mem: &wiggle::GuestMemory, location:", "iovec_metadata",
             ["MemRead(buf pointer)", "MemRead(buf_len)"], "Generated record layout and field-offset checked addition; capture actual expansion."),
        node("guest_scalar_read", "crates/wiggle/src/guest_type.rs", "fn read(mem: &GuestMemory, ptr: GuestPtr<Self>) -> Result<Self, GuestError> {\n                // Use", "iovec_metadata",
             ["MemRead(checked scalar)"], "Macro-generated primitive loads: range, alignment, conversion, atomic/unsafe bridge."),
        node("lazy_context", P1, "fn transact(&mut self)", "uninitialized_adapter",
             ["dependency effects unresolved"], "Trace Descriptors::new and initial resource provisioning; first slice assumes an initialized authorized table."),
        node("descriptor_lookup", P1, "fn get_descriptor(&self, fd:", "all",
             ["FdAccess(model only)"], "Establish per-instance mapping, type, rights and handle lifetime."),
        node("fd_read", P1, "async fn fd_read(", "all",
             [], "Compose all branches, errors, position state, generated output, and call-site effects."),
        node("guest_destination", "crates/wiggle/src/lib.rs", "pub fn as_slice_mut(", "file_direct_or_worker",
             [], "Tie the returned slice to the validated range and actual live allocation."),
        node("range_arithmetic", "crates/wiggle/src/bounds.rs", "pub(crate) fn checked_range_end(", "range_validation",
             [], "Production byte-range arithmetic checked by Flux.",
             "proved_arithmetic_only" if hashlib.sha256(source("crates/wiggle/src/bounds.rs").encode()).hexdigest() == PROVED_BOUNDS_SHA256 else "unproved_changed_since_evidence"),
        node("file_backend", "crates/wasi/src/filesystem/unix.rs", "pub(crate) fn read_at_cursor_unspecified(", "file_direct_and_worker",
             [], "With p1 delegates to checked memory_policy::read_at; outer delegate/caller not yet checked."),
        node("policy_root", MEMORY_POLICY, "pub fn new(memory:", "actual_borrowed_region",
             [], "Capture actual slice pointer and extent; Rust borrow rules and Flux pointer specs trusted. Calling guest selection remains open.", memory_status),
        node("policy_write", MEMORY_POLICY, "pub fn write(&mut self,", "actual_borrowed_region",
             [], "Validate range, form exact real pointer and retain region extent and exclusive borrow.", memory_status),
        node("policy_copy", MEMORY_POLICY, "pub fn copy_bytes(", "unshared_copy_back",
             ["MemRead(source slice)", "MemWrite(destination slice)"], "Checked permit consumer performs real ptr::copy using Flux external copy specification.", memory_status),
        node("policy_read", MEMORY_POLICY, "pub fn read_at(\n", "file_direct_and_worker",
             ["MemWrite(destination capacity, external OS assumption)"], "Checked construction and consumption of actual-slice permit; success count bounded by capacity under trusted adapter contract.", memory_status),
        node("os_read_adapter", MEMORY_POLICY, "unsafe fn os_read_at(", "unix_file_read",
             ["MemWrite(destination capacity, assumed)", "FdAccess(file, authorization unproved)"], "One trusted body: raw slice/std/libc/kernel; signature checks pointer capacity and success count. Write footprint/framing externally assumed, not proved heap effects.", "trusted_external_contract"),
        node("worker_dispatch", "crates/wasi/src/filesystem.rs", "pub(crate) async fn run_blocking<F, R>(&self, body: F) -> R\n    where\n        F: FnOnce(&std::fs::File) -> R + Send + 'static,\n        R: Send + 'static,\n    {\n        match self.as_blocking_file()", "file_worker",
             [], "Owned Vec and Arc<File> across suspension; this function may execute inline or spawn."),
        node("worker_spawn", "crates/wasi/src/filesystem.rs", "pub(crate) fn spawn_blocking<F, R>(&self", "file_worker",
             [], "Track cloned file lifetime and owned buffer; no borrowed guest pointer in closure."),
        node("task_spawn", "crates/wasi/src/runtime.rs", "pub fn spawn_blocking<F, R>(f:", "file_worker",
             ["scheduler effects outside model"], "Dropping/aborting a handle does not by itself prove a running blocking OS call has stopped."),
        node("copy_back", "crates/wiggle/src/lib.rs", "pub fn copy_from_bytes(", "file_worker_and_stdin",
             [], "Unproved outer method validates sizes; unshared destination delegates to checked policy copy. Empty copy returns early."),
        node("shared_copy", "crates/wiggle/src/lib.rs", "pub fn copy_from_slice<T>(", "shared_memory_excluded",
             ["MemRead(source)", "MemWrite(shared destination)"], "Legacy generic-copy fallback remains outside initial unshared-memory proof profile."),
        node("typed_destination", "crates/wiggle/src/lib.rs", "pub(crate) fn validate_size_align_mut<T>(", "shared_copy_and_generated_store",
             [], "Checked element-size multiplication, conversion, range, alignment, and Ranges borrow."),
        node("generated_store", "crates/wiggle/generate/src/funcs.rs", "Instruction::Store { ty } =>", "successful_return",
             ["MemWrite(nread: 4 bytes)"], "Actual wrapper captured. Prove result-pointer validity, store ordering, aliases and traps."),
        node("primitive_store", "crates/wiggle/src/guest_type.rs", "fn write(mem: &mut GuestMemory, ptr: GuestPtr<Self>, val: Self) -> Result<(), GuestError> {\n                // See", "generated_nread_store",
             ["MemWrite(checked scalar)"], "Macro-generated u32 store; atomic cast/store bridge and alignment remain unproved."),
    ]
    next(n for n in nodes if n["id"] == "generated_store")["expanded_evidence"] = location(
        GLUE, "memory.write(wiggle::GuestPtr::<Size>::new(arg3 as u32),")
    edges = [
        ["caller_memory", "iovec_selection", "generated fd_read ABI dispatch"],
        ["iovec_selection", "generated_iovec_record", "each descriptor actually traversed"],
        ["generated_iovec_record", "guest_scalar_read", "generated buf and buf_len field loads"],
        ["iovec_selection", "lazy_context", "transact; may initialize descriptors"],
        ["lazy_context", "descriptor_lookup", "table initialized or reused"],
        ["descriptor_lookup", "fd_read", "File / Stdin / Badf branches"],
        ["fd_read", "guest_destination", "file branch, including before worker fallback"],
        ["guest_destination", "range_arithmetic", "through validate_range"],
        ["guest_destination", "file_backend", "direct: blocking permitted and guest slice borrowable"],
        ["guest_destination", "worker_dispatch", "fallback: owned zero-initialized Vec"],
        ["worker_dispatch", "worker_spawn", "blocking on current thread not permitted"],
        ["worker_spawn", "task_spawn", "closure owns buffer and cloned file"],
        ["worker_dispatch", "file_backend", "inline or worker closure"],
        ["file_backend", "copy_back", "worker success; truncate Vec and form prefix iov"],
        ["file_backend", "policy_read", "p1 actual read destination"],
        ["policy_read", "policy_root", "capture actual destination borrow"],
        ["policy_read", "policy_write", "whole destination permit"],
        ["policy_write", "range_arithmetic", "start/count validation"],
        ["policy_read", "os_read_adapter", "WriteAccess::read_at passes bounded pointer/count"],
        ["copy_back", "guest_destination", "nonempty unshared destination"],
        ["copy_back", "policy_copy", "nonempty unshared byte copy"],
        ["policy_copy", "policy_root", "capture actual destination borrow"],
        ["policy_copy", "policy_write", "whole destination permit"],
        ["copy_back", "shared_copy", "shared-memory fallback, excluded"],
        ["shared_copy", "typed_destination", "legacy generic destination"],
        ["typed_destination", "range_arithmetic", "Ranges path or general validate_range"],
        ["fd_read", "generated_store", "success after position checked_add/store"],
        ["generated_store", "primitive_store", "memory.write::<u32>"],
        ["primitive_store", "typed_destination", "validate scalar destination"],
    ]
    paths = sorted({WITX, P1, GLUE, GLUE_METADATA, "Cargo.toml", "Cargo.lock", "crates/wasi/Cargo.toml", "crates/wasi/witx/p1/typenames.witx", *[n["source"]["path"] for n in nodes]})
    return {
        "schema_version": 1,
        "claim": "ABI accounting and partial reviewed source graph; not verified hostcall coverage or graph completeness",
        "pins": {"upstream_wasmtime": "7c83a428028b44e1a73b40aa6a912d6700983624",
                 "integration_baseline": "7f3dc0a6aed721b6f72a1cc5e6107a548d2bca17",
                 "rustc": "1a2c4797ef2570bd76ca5dee34449169bc7dc457",
                 "target": "x86_64-unknown-linux-gnu", "wasi_features": ["p1", "p2"],
                 "flux": "b68c177c5ace7cb3644fdeea140dc5d18669c6cc"},
        "export_count": len(rows), "exports": rows,
        "arithmetic_evidence": {"run": "https://github.com/sji005/wasmtime/actions/runs/43987832550",
                                "source_sha256": PROVED_BOUNDS_SHA256},
        "production_memory_evidence": {"run": "https://github.com/sji005/wasmtime/actions/runs/44004096275",
                                       "code_revision": "64bcdbe1ff60200bfe16d0872a3baeb4abd61d49",
                                       "source_sha256": PROVED_MEMORY_SHA256,
                                       "functions_checked": 11, "functions_trusted": 1,
                                       "constraints_solved": 38, "negative_mutations_rejected": 5,
                                       "claim": "Checked module operations relative to supplied valid slices and external specs; no whole-hostcall proof"},
        "expanded_binding_evidence": {"run": "https://github.com/sji005/wasmtime/actions/runs/43993427124",
                                      "code_revision": "14321e36f1f27e289d88f970003706d478460542",
                                      "metadata": GLUE_METADATA, "wrapper": GLUE,
                                      "sha256": glue_evidence["wrapper_sha256"], "proof_status": "captured_unproved"},
        "fd_read": {"nodes": nodes, "edges": edges,
                    "external_chain": [
                        {"layer": "Wasmtime", "operation": "read_at_cursor_unspecified -> memory_policy::read_at -> trusted os_read_at -> FileExt::read_at"},
                        {"layer": "pinned Rust std", "path": "library/std/src/sys/fs/unix.rs", "line": 1496, "operation": "File::read_at -> FileDesc::read_at"},
                        {"layer": "pinned Rust std", "path": "library/std/src/sys/fd/unix.rs", "line": 191, "operation": "libc::pread64(fd, ptr, min(len, READ_LIMIT), offset)"},
                        {"layer": "libc / Linux", "operation": "pread64 wrapper and kernel boundary", "status": "bounded adapter contract assumed; deployed glibc/kernel implementation not verified"}],
                    "excluded_or_unresolved": ["stdin/custom HostInputStream dispatch", "lazy initial descriptor provisioning effects", "Flux proof of expanded fd_read glue", "transitive scheduler/logging/allocation syscalls", "shared memory", "reentrancy/cancellation proof", "kernel and libc implementation"]},
        "source_sha256_lf_utf8": {path: hashlib.sha256(source(path).encode()).hexdigest() for path in paths},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    encoded = json.dumps(build(), indent=2) + "\n"
    if args.check:
        if not TARGET.exists() or TARGET.read_text(encoding="utf-8") != encoded:
            raise SystemExit("Inventory drift: review source changes and run python3 verification/flux/inventory.py")
        print("PASS: all 46 P1 exports accounted for; inspected source inventory unchanged")
    else:
        TARGET.write_text(encoded, encoding="utf-8", newline="\n")
        print(TARGET)


if __name__ == "__main__":
    main()
