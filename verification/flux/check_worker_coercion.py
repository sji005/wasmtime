#!/usr/bin/env python3
"""Isolate the worker's Vec-to-slice refinement inference in pinned Flux."""

import json
import os
from pathlib import Path
import subprocess

from check_environment import ROOT, TARGET, TOOLCHAIN

PRELUDE = """use std::{fs::File, io, os::unix::fs::FileExt};

#[cfg_attr(flux, flux::sig(fn(&File, &mut [u8][@n]) -> Result<usize{c: c <= n}, io::Error>))]
fn read_into(file: &File, buf: &mut [u8]) -> io::Result<usize> {
    file.read_at(buf, 0)
}
"""

CASES = {
    "slice": """pub fn worker(file: &File, buf: &mut [u8]) -> io::Result<usize> {
    read_into(file, buf)
}
""",
    "vec": """pub fn worker(file: &File, mut buf: Vec<u8>) -> io::Result<usize> {
    read_into(file, &mut buf)
}
""",
    "allocated-vec": """pub fn worker(file: &File, n: usize) -> io::Result<usize> {
    let mut buf = vec![0; n];
    read_into(file, &mut buf)
}
""",
    "captured-vec": """pub fn worker(file: &File, n: usize) -> io::Result<Vec<u8>> {
    let mut buf = vec![0; n];
    let read = move || {
        let count = read_into(file, &mut buf)?;
        buf.truncate(count);
        Ok(buf)
    };
    read()
}
""",
}

CAPTURE_BOUNDS = """#[cfg_attr(flux, flux::sig(fn(&mut [u8]{n: n > 0})))]
fn needs_room(_buf: &mut [u8]) {}

fn invoke(work: impl FnOnce() -> Vec<u8>) -> Vec<u8> {
    work()
}

#[cfg_attr(flux, flux::sig(fn(Vec<u8>{v: v.len > 0}) -> Vec<u8>))]
pub fn worker(mut buf: Vec<u8>) -> Vec<u8> {
    invoke(move || {
        needs_room(&mut buf);
        buf
    })
}
"""


def main():
    output = ROOT / "artifacts/fd-read/worker-coercion"
    output.mkdir(parents=True, exist_ok=True)
    primitive = json.loads(Path(os.environ["FD_READ_PRIMITIVE_MANIFEST"]).read_text())
    env = dict(os.environ, RUSTUP_TOOLCHAIN=TOOLCHAIN)
    report = {"scope": "Checker diagnostics for a minimal worker-shaped Rust program", "cases": []}
    cases = {name: PRELUDE + body for name, body in CASES.items()}
    cases["nonempty-capture"] = CAPTURE_BOUNDS
    cases["missing-capture-bound"] = CAPTURE_BOUNDS.replace("Vec<u8>{v: v.len > 0}", "Vec<u8>")
    for name, source in cases.items():
        path = output / (name.replace("-", "_") + ".rs")
        path.write_text(source)
        case = {"name": name, "runs": []}
        report["cases"].append(case)
        for tool in ("rustc", "flux"):
            command = [tool, "--edition=2024", "--crate-type=lib", "--target", TARGET, "--color=never",
                       "--out-dir", str(output)]
            if tool == "flux":
                command += ["--cfg", "flux", "-Fcheck-overflow=strict", "-Fstd-extern-specs=on", "-Fdump-rty=on",
                            "-Fallow-raw-deref=none", "-Flog-dir=" + str(output / name), "-Zunstable-options"]
                for extension in ("rlib", "rmeta"):
                    command += ["--extern", "force:fd_read_file_primitive=" + primitive["artifacts"][extension]]
                command += ["-L", "dependency=" + str(Path(primitive["artifacts"]["rmeta"]).parent)]
            command.append(str(path))
            result = subprocess.run(command, cwd=ROOT, env=env, text=True, capture_output=True, timeout=120)
            log = result.stdout + result.stderr
            log_name = f"{name}-{tool}.log"
            (output / log_name).write_text(log)
            case["runs"].append({"command": command, "log": log_name, "exit_code": result.returncode})
            if tool == "rustc" and result.returncode:
                raise RuntimeError("Ordinary Rust failed: " + log)
            if tool == "flux":
                if name == "missing-capture-bound" and result.returncode and "a precondition cannot be proved" in log:
                    case["status"] = "rejected-missing-precondition"
                elif result.returncode == 0 and (
                    "2 checked; 0 trusted; 0 ignored" in log or "3 checked; 0 trusted; 0 ignored" in log
                ):
                    case["status"] = "checked"
                elif "parameter inference error at function call" in log:
                    case["status"] = "open-parameter-inference"
                else:
                    case["status"] = "open-other-diagnostic"
                if name == "slice" and case["status"] != "checked":
                    raise RuntimeError("Direct slice control failed: " + log)
                print(f"Worker coercion {name}: {case['status']}", flush=True)
            (output / "worker-coercion.json").write_text(json.dumps(report, indent=2) + "\n")
    statuses = {case["name"]: case["status"] for case in report["cases"]}
    if statuses["nonempty-capture"] == "checked" and statuses["missing-capture-bound"] != "rejected-missing-precondition":
        raise RuntimeError("Captured mutable buffer without its required bound should fail")


if __name__ == "__main__":
    main()
