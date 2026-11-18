#!/usr/bin/env python3
"""Keep associated-field normalization distinct from Wasmtime safety proofs."""

import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "artifacts/fd-read/compat-projection"
SOURCE = '''#![allow(dead_code)]
#[cfg(flux)] extern crate flux_core;
trait Pointee { type Pointer; }
impl<T> Pointee for [T] { type Pointer = (u32, u32); }
struct Ptr<T: ?Sized + Pointee> { pointer: T::Pointer }
pub fn count<T>(pointer: &Ptr<[T]>) -> u32 { pointer.pointer.1 }
'''


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, RUSTUP_TOOLCHAIN="nightly-2026-10-22")
    report = {"scope": "checker regression only; no reimplementation of a Wasmtime helper is proved", "runs": []}
    flags = ["--edition=2024", "--crate-type=lib", "--color=never", "--out-dir", str(OUT)]
    proof = ["--cfg", "flux", "-Fcheck-overflow=strict", "-Fallow-raw-deref=none", "-Flog-dir=" + str(OUT / "flux-log")]
    for name, source in (
        ("positive", SOURCE),
        ("bad-postcondition", SOURCE.replace("pub fn count", "#[cfg_attr(flux, flux::sig(fn(&Ptr<[T]>) -> u32[0]))]\npub fn count")),
    ):
        path = OUT / (name.replace("-", "_") + ".rs")
        path.write_text(source)
        variants = [("rustc", [], env)]
        if name == "positive":
            baseline = dict(env)
            baseline.pop("FLUX_DRIVER", None)
            baseline.pop("FLUX_COMPAT_RECEIPT", None)
            variants.append(("baseline", proof, baseline))
        variants.append(("candidate", proof, env))
        for kind, extra, selected_env in variants:
            command = ["rustc" if kind == "rustc" else "flux", *flags, *extra, str(path)]
            result = subprocess.run(command, cwd=ROOT, env=selected_env, text=True, capture_output=True, timeout=120)
            log = result.stdout + result.stderr
            log_name = f"{name}-{kind}.log"
            (OUT / log_name).write_text(log)
            report["runs"].append({"name": name, "kind": kind, "command": command, "exit_code": result.returncode, "log": log_name})
            (OUT / "projection.json").write_text(json.dumps(report, indent=2) + "\n")
            if kind == "rustc" and result.returncode:
                raise RuntimeError("ordinary Rust failed: " + log)
            if kind == "candidate":
                if name == "positive" and (result.returncode or "1 checked; 0 trusted; 0 ignored" not in log):
                    raise RuntimeError("candidate failed normalization regression: " + log)
                if name != "positive" and (not result.returncode or "error[E0999]: refinement type error" not in log):
                    raise RuntimeError("bad postcondition was not rejected: " + log)
                if "internal compiler error" in log or "internal flux error" in log:
                    raise RuntimeError("candidate crashed: " + log)
    report["status"] = "passed"
    (OUT / "projection.json").write_text(json.dumps(report, indent=2) + "\n")
    print("PASS: associated field normalization and rejected bad postcondition; checker regression only")


if __name__ == "__main__":
    main()
