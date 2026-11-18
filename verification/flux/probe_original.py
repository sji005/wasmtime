#!/usr/bin/env python3
"""Collect pinned-checker feasibility diagnostics on original production bodies.

This driver has no spatial postcondition and establishes no fd_read theorem.
It forwards Cargo's real compiler invocation to Flux for one selected crate and
source span. It neither extracts bodies nor substitutes simplified types/callees.
Unselected bodies/dependencies are UNCHECKED, never implicitly verified.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
TARGET = "x86_64-unknown-linux-gnu"
FLAGS = ["-Fcheck-overflow=strict", "-Fallow-raw-deref=none", "-Fstd-extern-specs=on", "-Ffixpoint-timeout=30"]

# Exact original-source anchors select a function, not an incidental substring
# such as fd_readdir when the intended function is fd_read.
CASES = [
    ("pointer-new", "wiggle", "crates/wiggle/src/lib.rs", "    pub fn new(pointer: T::Pointer)", ["--all-features"]),
    ("pointer-offset", "wiggle", "crates/wiggle/src/lib.rs", "    pub fn offset(&self)", ["--all-features"]),
    ("pointer-cast", "wiggle", "crates/wiggle/src/lib.rs", "    pub fn cast<U>", ["--all-features"]),
    ("pointer-array", "wiggle", "crates/wiggle/src/lib.rs", "    pub fn as_array(&self", ["--all-features"]),
    ("pointer-base", "wiggle", "crates/wiggle/src/lib.rs", "    pub fn offset_base(&self) -> u32", ["--all-features"]),
    ("pointer-len", "wiggle", "crates/wiggle/src/lib.rs", "    pub fn len(&self) -> u32", ["--all-features"]),
    ("pointer-as-ptr", "wiggle", "crates/wiggle/src/lib.rs", "    pub fn as_ptr(&self)", ["--all-features"]),
    ("range", "wiggle", "crates/wiggle/src/lib.rs", "    fn validate_range<T>", ["--all-features"]),
    ("typed-read-range", "wiggle", "crates/wiggle/src/lib.rs", "    fn validate_size_align<T>", ["--all-features"]),
    ("typed-write-range", "wiggle", "crates/wiggle/src/lib.rs", "    pub(crate) fn validate_size_align_mut<T>", ["--all-features"]),
    ("align-cells", "wiggle", "crates/wiggle/src/lib.rs", "    fn align_cells<T>", ["--all-features"]),
    ("payload-slice", "wiggle", "crates/wiggle/src/lib.rs", "    pub fn as_slice_mut(", ["--all-features"]),
    ("copy-back", "wiggle", "crates/wiggle/src/lib.rs", "    pub fn copy_from_slice<T>", ["--all-features"]),
    ("pointer-add", "wiggle", "crates/wiggle/src/lib.rs", "    pub fn add(", ["--all-features"]),
    ("pointer-iter", "wiggle", "crates/wiggle/src/lib.rs", "    pub fn iter(", ["--all-features"]),
    ("pointer-subrange", "wiggle", "crates/wiggle/src/lib.rs", "    pub fn get_range(", ["--all-features"]),
    ("memory-slice", "wasmtime", "crates/wasmtime/src/runtime/memory.rs", "    fn into_range_mut(", ["--no-default-features", "--features", "runtime,std,component-model,async"]),
    ("iovec-selector", "wasmtime-wasi", "crates/wasi/src/p1.rs", "    fn first_non_empty_iovec(", ["--no-default-features", "--features", "p1"]),
    ("fd-read-caller", "wasmtime-wasi", "crates/wasi/src/p1.rs", "    async fn fd_read(", ["--no-default-features", "--features", "p1"]),
    ("unix-read-adapter", "wasmtime-wasi", "crates/wasi/src/filesystem/unix.rs", "pub(crate) fn read_at_cursor_unspecified(", ["--no-default-features", "--features", "p1"]),
]


def wrap(arguments):
    compiler, *rustargs = arguments
    selected = os.environ["FD_READ_PROBE_CRATE"]
    crate = rustargs[rustargs.index("--crate-name") + 1] if "--crate-name" in rustargs else None
    command = [compiler, *rustargs]
    if crate == selected:
        output = Path(os.environ["FD_READ_PROBE_OUTPUT"])
        if "FD_READ_SOURCE_COPY" in os.environ:
            package_dir = {"wasmtime_wasi": "wasi", "wiggle": "wiggle"}.get(selected)
            if package_dir is None:
                raise RuntimeError("Unregistered source-copy package")
            relative_root = f"crates/{package_dir}/src/lib.rs"
            original_root = ROOT / relative_root
            matches = [i for i, value in enumerate(rustargs) if value.endswith(relative_root) or value == str(original_root)]
            if len(matches) != 1:
                raise RuntimeError("Unexpected source-copy compiler context")
            rustargs[matches[0]] = str(Path(os.environ["FD_READ_SOURCE_COPY"]) / "src/lib.rs")
        if os.environ.get("FD_READ_PROBE_MODE") == "ordinary":
            command = [compiler, *rustargs]
            (output / "ordinary-compiler-invocation.json").write_text(json.dumps(command, indent=2) + "\n")
            return subprocess.run(command, close_fds=False).returncode
        command = ["flux", *rustargs, *FLAGS, "-Ffull-compilation=on",
                   f"-Finclude={os.environ['FD_READ_PROBE_SELECTOR']}",
                   f"-Flog-dir={output / 'flux-log'}"]
        if selected in ("wasmtime_wasi", "wiggle") and "FD_READ_PRIMITIVE_MANIFEST" in os.environ:
            primitive = json.loads(Path(os.environ["FD_READ_PRIMITIVE_MANIFEST"]).read_text())
            command.append("-Zunstable-options")
            for kind in ("rmeta", "rlib"):
                command.extend(["--extern", "force:fd_read_file_primitive=" + primitive["artifacts"][kind]])
            command.extend(["-L", "dependency=" + str(Path(primitive["artifacts"]["rmeta"]).parent)])
        (output / "compiler-invocation.json").write_text(json.dumps(command, indent=2) + "\n")
        print("FD_READ_ACTUAL_BODY: " + json.dumps(command), flush=True)
    return subprocess.run(command, close_fds=False).returncode


def classify(code, log, invoked):
    if not invoked:
        return "infrastructure-no-flux-invocation"
    if re.search(r"(?i)(unsupported|not supported|internal compiler error|internal flux error|panicked at|not yet implemented)", log):
        return "open-checker-limitation"
    if re.search(r"error\[E0999\]: (mismatched sorts|no field|invalid refinement|cannot refine|expected a sort|.*primitive sort.*doesn't have fields)", log):
        return "open-specification-error"
    if re.search(r"error\[E0999\]: (refinement type error|arithmetic operation may (over|under)flow|type invariant may not hold)", log):
        return "open-refinement-obligation-not-a-bug-finding"
    if code == 0 and re.search(r"[1-9]\d* checked;", log):
        return "feasibility-only-no-spatial-postcondition"
    return "open-unclassified-diagnostic" if code else "infrastructure-no-checked-body"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--case", action="append", choices=[c[0] for c in CASES])
    args = parser.parse_args()
    if platform.system() != "Linux" or platform.machine() != "x86_64":
        parser.error("original-body checker probes require x86-64 Linux")
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    gate = json.loads((ROOT / "artifacts/fd-read/environment/environment.json").read_text())
    if gate["status"] != "passed":
        parser.error("M0 smoke gate must pass before original-body probes")
    wrapper = output / "rustc-wrapper"
    wrapper.write_text(
        "#!/usr/bin/env python3\nimport sys\nsys.path.insert(0, "
        + repr(str(HERE)) + ")\nfrom probe_original import wrap\nsys.exit(wrap(sys.argv[1:]))\n"
    )
    wrapper.chmod(0o755)
    report = {
        "claim": "Checker feasibility only; original bodies, no spatial theorem",
        "source_revision": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "pins": json.loads((HERE / "pins.json").read_text()),
        "checker_variant": json.loads(Path(os.environ["FLUX_COMPAT_RECEIPT"]).read_text()) if "FLUX_COMPAT_RECEIPT" in os.environ else "unmodified pinned baseline",
        "external_file_primitive": json.loads(Path(os.environ["FD_READ_PRIMITIVE_MANIFEST"]).read_text()) if "FD_READ_PRIMITIVE_MANIFEST" in os.environ else None,
        "target": TARGET,
        "explicitly_trusted_local_bodies": [],
        "explicitly_ignored_local_bodies": [],
        "unchecked": "Every unselected body/dependency remains unverified; Flux counts excluded functions as trusted. No spatial postcondition or caller contract is discharged by this probe.",
        "cases": [],
    }
    for name, package, source, anchor, features in CASES:
        if args.case and name not in args.case:
            continue
        text = (ROOT / source).read_text()
        expected_count = 2 if name in ("pointer-base", "pointer-len") else 1
        if text.count(anchor) != expected_count:
            raise RuntimeError(f"Original source anchor changed or ambiguous: {name}")
        line = text[:text.index(anchor)].count("\n") + 1 + anchor.count("\n")
        last_line = anchor.split("\n")[-1]
        column = len(last_line) - len(last_line.lstrip()) + 1
        selector = f"span:{source}:{line}:{column}"
        case_dir = output / name
        case_dir.mkdir(exist_ok=True)
        env = dict(os.environ, RUSTUP_TOOLCHAIN="nightly-2026-10-22", CARGO_INCREMENTAL="0", CARGO_TERM_COLOR="never")
        # Ordinary compilation must pass independently of any Flux diagnostic.
        ordinary = ["cargo", "check", "--locked", "--target", TARGET, "-p", package, *features, "--lib"]
        rust = subprocess.run(ordinary, cwd=ROOT, env=env, text=True, capture_output=True, timeout=900)
        (case_dir / "rust.log").write_text(rust.stdout + rust.stderr)
        if rust.returncode:
            raise RuntimeError(f"Ordinary Rust compilation failed for {name}; not a Flux rejection")
        env.update(RUSTC_WORKSPACE_WRAPPER=str(wrapper), FD_READ_PROBE_CRATE=package.replace("-", "_"),
                   FD_READ_PROBE_OUTPUT=str(case_dir), FD_READ_PROBE_SELECTOR=selector)
        command = ["cargo", "rustc", "--locked", "--target", TARGET, "-p", package, *features,
                   "--lib", "--", "--cfg", "fd_read_probe_" + name.replace("-", "_")]
        print("+", " ".join(command), flush=True)
        try:
            result = subprocess.run(command, cwd=ROOT, env=env, text=True, capture_output=True, timeout=900)
            log = result.stdout + result.stderr
            code = result.returncode
        except subprocess.TimeoutExpired as error:
            def decode(value):
                return value.decode(errors="replace") if isinstance(value, bytes) else (value or "")
            log = decode(error.stdout) + decode(error.stderr) + "\nChecker probe timed out.\n"
            code = 124
        (case_dir / "flux.log").write_text(log)
        status = classify(code, log, (case_dir / "compiler-invocation.json").is_file())
        if name == "range" and status == "feasibility-only-no-spatial-postcondition":
            status = "conditional-slice-bound-checked-mutations-required"
        report["cases"].append({
            "name": name, "package": package, "features": features, "source": source,
            "source_sha256_lf": hashlib.sha256(text.encode()).hexdigest(),
            "selector": selector, "ordinary_command": ordinary, "flux_command": command,
            "exit_code": code, "status": status, "log": f"{name}/flux.log",
        })
        (output / "original-body-probes.json").write_text(json.dumps(report, indent=2) + "\n")
        # Full logs remain artifacts; print diagnostics without flooding CI logs.
        diagnostic = [s for s in log.splitlines() if s.lstrip().startswith(("error[", "error:", "summary."))]
        print(f"{name}: {status}\n" + "\n".join(diagnostic[:12]), flush=True)
    print("Probe collection finished; no production spatial proof is claimed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
