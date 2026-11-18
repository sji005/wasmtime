#!/usr/bin/env python3
"""M0: require real Flux success and well-typed refinement/overflow rejections.

Exit 2 means unavailable infrastructure; it never means a failed safety proof.
All diagnostics, commands and source digests are retained in --output-dir.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
TOOLCHAIN = "nightly-2026-10-22"
TARGET = "x86_64-unknown-linux-gnu"
DIAGNOSTIC = re.compile(
    r"error\[E0999\]: (refinement type error|arithmetic operation may (over|under)flow|assertion might fail: possible out-of-bounds access)"
)
SUMMARY = re.compile(r"3 functions processed: 3 checked; 0 trusted; 0 ignored\.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, RUSTUP_TOOLCHAIN=TOOLCHAIN)
    report = {
        "claim": "M0 checker compatibility only; no production function checked",
        "status": "unavailable",
        "host": platform.platform(),
        "target": TARGET,
        "toolchain": TOOLCHAIN,
        "pins": json.loads((HERE / "pins.json").read_text()),
        "frozen_sources": json.loads((HERE / "sources.json").read_text()),
        "harness_inputs_sha256": {
            name: hashlib.sha256((HERE / name).read_bytes()).hexdigest()
            for name in ("check_environment.py", "smoke.rs", "pins.json")
        },
        "source_revision": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "working_tree": subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=ROOT, text=True
        ),
        "runs": [],
        "checked_production_bodies": [],
        "trusted_local_bodies": [],
        "ignored_local_bodies": [],
    }

    def save():
        (output / "environment.json").write_text(
            json.dumps(report, indent=2) + "\n", encoding="utf-8"
        )

    def run(name, command):
        print("+", " ".join(map(str, command)), flush=True)
        result = subprocess.run(
            list(map(str, command)), cwd=ROOT, env=env, text=True,
            capture_output=True, timeout=120,
        )
        log = result.stdout + result.stderr
        (output / f"{name}.log").write_text(log, encoding="utf-8")
        report["runs"].append({
            "name": name, "command": list(map(str, command)),
            "exit_code": result.returncode, "log": f"{name}.log",
        })
        save()
        print(log, flush=True)
        return result.returncode, log

    try:
        if platform.system() != "Linux" or platform.machine() not in ("x86_64", "AMD64"):
            raise FileNotFoundError("The pinned Flux experiment requires x86-64 Linux; native Windows is not a validated checker host.")
        for tool in ("rustc", "flux", "z3", "fixpoint"):
            if not shutil.which(tool):
                raise FileNotFoundError(f"Missing tool: {tool}")
        for tool, flags in (("rustc", ["-vV"]), ("flux", ["--version"]), ("z3", ["--version"]), ("fixpoint", ["--version"])):
            code, log = run(f"version-{tool}", [tool, *flags])
            if code:
                raise RuntimeError(f"Cannot identify {tool}")
            if tool == "rustc" and f"host: {TARGET}" not in log:
                raise RuntimeError("Unexpected Rust host target")
        original = (HERE / "smoke.rs").read_text(encoding="utf-8")
        flags = ["--edition=2024", "--crate-type=lib", "--color=never", "--target", TARGET, "--out-dir", output]
        proof = ["--cfg", "flux", "-Fcheck-overflow=strict", "-Fallow-raw-deref=none"]
        probes = {
            "positive": original,
            "bad-addition": original.replace("    x + y\n", "    x + y + 1\n"),
            "bad-slice": original.replace("    bytes[index]\n", "    bytes[bytes.len()]\n"),
            "bad-pointer-width": original.replace("destination.as_mut_ptr(), 1)", "destination.as_mut_ptr(), 2)"),
        }
        for name, source in probes.items():
            if name != "positive" and source == original:
                raise RuntimeError(f"Missing mutation anchor: {name}")
            path = output / f"{name.replace('-', '_')}.rs"
            path.write_text(source, encoding="utf-8")
            report.setdefault("source_sha256", {})[name] = hashlib.sha256(source.encode()).hexdigest()
            code, _ = run(f"{name}-rustc", ["rustc", *flags, path])
            if code:
                raise RuntimeError(f"{name}: ordinary Rust compilation failed (not a proof rejection)")
            code, log = run(f"{name}-flux", ["flux", *flags, *proof, path])
            if name == "positive":
                if code or not SUMMARY.search(log):
                    raise RuntimeError("Positive probes did not check exactly three untrusted, unignored bodies")
            elif code == 0 or not DIAGNOSTIC.search(log):
                raise RuntimeError(f"{name}: expected refinement/overflow/bounds diagnostic; infrastructure/syntax failures do not count")
            if re.search(r"(?i)(internal compiler error|solver.*(crash|timeout)|unsupported)", log):
                raise RuntimeError(f"{name}: unresolved checker/solver limitation")
        report["status"] = "passed"
        print("PASS: M0 smoke probes only; no fd_read proof is claimed")
        return 0
    except (FileNotFoundError, subprocess.TimeoutExpired) as error:
        report["reason"] = str(error)
        print(f"UNAVAILABLE: {error}", file=sys.stderr)
        return 2
    except (RuntimeError, OSError) as error:
        report["status"] = "failed-environment-gate"
        report["reason"] = str(error)
        print(f"M0 NOT PASSED: {error}", file=sys.stderr)
        return 1
    finally:
        save()


if __name__ == "__main__":
    sys.exit(main())
