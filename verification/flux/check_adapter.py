#!/usr/bin/env python3
"""Check an exact source slice of the existing Unix forwarding adapter.

The original crate probe hits an unrelated bitflags ICE. This narrower experiment
preserves the entire original function and all three std imports byte-for-byte
(apart from LF normalization), with no stubs or replacement arithmetic. Its
result-count proof is not a proof of the original crate or its fd_read callers.
Keep that linkage limitation visible even if this narrower experiment passes.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

from check_environment import ROOT, HERE, TARGET, TOOLCHAIN, DIAGNOSTIC


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--external-specs", action="store_true")
    args = parser.parse_args()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    source_path = "crates/wasi/src/filesystem/unix.rs"
    source = (ROOT / source_path).read_text()
    entry = json.loads((HERE / "annotations.json").read_text())[source_path][0]
    start = source.index(entry["annotation"] + entry["anchor"])
    body = source.index("{", start + len(entry["annotation"]))
    end = source.index("\n}", body) + 2
    original = source[start:end] + "\n"
    imports = "use std::fs::File;\nuse std::io;\nuse std::os::unix::fs::FileExt;\n"
    for line in imports.splitlines():
        assert source.count(line) == 1, f"original std import changed: {line}"
    header = "#![allow(dead_code)]\n#[cfg(flux)] extern crate flux_core;\n#[cfg(flux)] extern crate flux_rs;\n#[cfg(flux)] #[path = " + json.dumps(str(HERE / "file_read_specs.rs")) + "] mod file_read_specs;\n"
    if args.external_specs:
        header = "#![allow(dead_code)]\n#[cfg(flux)] extern crate flux_core;\n"
    env = dict(os.environ, RUSTUP_TOOLCHAIN=TOOLCHAIN)
    flags = ["--edition=2024", "--crate-type=lib", "--target", TARGET, "--color=never", "--out-dir", str(output)]
    proof = ["--cfg", "flux", "-Fcheck-overflow=strict", "-Fallow-raw-deref=none"]
    if args.external_specs:
        primitive = json.loads(Path(env["FD_READ_PRIMITIVE_MANIFEST"]).read_text())
        proof.append("-Zunstable-options")
        for kind in ("rmeta", "rlib"):
            proof.extend(["--extern", "force:fd_read_file_primitive=" + primitive["artifacts"][kind]])
        proof.extend(["-L", "dependency=" + str(Path(primitive["artifacts"]["rmeta"]).parent)])
    report = {
        "claim": "Narrow source-slice result-count experiment, not a production fd_read proof",
        "source": source_path,
        "source_revision": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "original_function_sha256_lf": hashlib.sha256(original.encode()).hexdigest(),
        "original_imports": imports,
        "trusted_external_primitive": "std::os::unix::fs::FileExt::read_at for std::fs::File only",
        "unencoded_assumptions": ["writes confined to supplied slice on all outcomes", "other allocations framed", "Rust reference lifetime/provenance"],
        "linkage": "Exact source/signature/imports retained; full-crate checker still crashes; callers and heap effects unchecked",
        "runs": [],
        "status": "open",
    }
    for name, function in (("original", original), ("bad-return-count", original.replace("file.read_at(buf, pos)", "Ok(usize::MAX)"))):
        if name != "original" and function == original:
            raise RuntimeError("mutation anchor changed")
        path = output / (name.replace("-", "_") + ".rs")
        path.write_text(header + imports + function)
        for tool, extra in (("rustc", []), ("flux", proof)):
            command = [tool, *flags, *extra, str(path)]
            result = subprocess.run(command, cwd=ROOT, env=env, text=True, capture_output=True, timeout=120)
            log = result.stdout + result.stderr
            (output / f"{name}-{tool}.log").write_text(log)
            report["runs"].append({"command": command, "exit_code": result.returncode, "log": f"{name}-{tool}.log"})
            (output / "adapter.json").write_text(json.dumps(report, indent=2) + "\n")
            print(log, flush=True)
            if tool == "rustc" and result.returncode:
                raise RuntimeError("ordinary Rust compilation failed; not proof rejection")
            if tool == "flux":
                if name == "original" and (result.returncode or not re.search(r"[1-9]\d* checked;", log)):
                    raise RuntimeError("source-slice experiment did not check")
                if name != "original" and (result.returncode == 0 or not DIAGNOSTIC.search(log)):
                    raise RuntimeError("bad result-count variant needs a real Flux proof rejection")
    report["status"] = "source-slice-count-contract-checked-full-crate-linkage-open"
    (output / "adapter.json").write_text(json.dumps(report, indent=2) + "\n")
    print("PASS: narrow adapter count experiment only; original crate and fd_read caller proof remain open")


if __name__ == "__main__":
    main()
