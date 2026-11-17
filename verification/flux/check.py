#!/usr/bin/env python3
"""Check the production bounds helper and require Flux to reject mutations."""

import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "crates/wiggle/src/bounds.rs"
TOOLCHAIN = "nightly-2026-10-22"


def run(command, **kwargs):
    print("+", " ".join(map(str, command)), flush=True)
    return subprocess.run(command, cwd=ROOT, text=True, **kwargs)


def main():
    env = dict(os.environ, RUSTUP_TOOLCHAIN=TOOLCHAIN)
    with tempfile.TemporaryDirectory(prefix="wiggle-flux-") as directory:
        output = Path(directory)
        flags = ["--edition=2024", "--crate-type=lib", "--out-dir", str(output)]
        proof_flags = ["--cfg", "flux", "-Fcheck-overflow=strict", "-Fallow-raw-deref=none"]
        run(["rustc", *flags, str(ROOT / "verification/flux/bounds.rs")], env=env, check=True)
        run(["flux", *flags, *proof_flags, str(ROOT / "verification/flux/bounds.rs")], env=env, check=True)

        original = SOURCE.read_text()
        mutations = {
            "off_by_one": ("Some(start + byte_len)", "Some(start + byte_len + 1)"),
            "missing_start_check": ("if start > memory_len {", "if false {"),
            "wrong_remaining_space": ("if byte_len > memory_len - start {", "if byte_len > memory_len {"),
            "reject_valid_ranges": ("Some(start + byte_len)", "None"),
        }
        for name, (before, after) in mutations.items():
            assert original.count(before) == 1, f"mutation anchor changed: {name}"
            mutant = output / f"{name}.rs"
            mutant.write_text(original.replace(before, after))
            # A syntax error or Rust compiler failure is not proof rejection.
            run(["rustc", *flags, str(mutant)], env=env, check=True)
            result = run(["flux", *flags, *proof_flags, str(mutant)], env=env, capture_output=True)
            log = result.stdout + result.stderr
            print(log, flush=True)
            if result.returncode == 0 or "error[FLUX]" not in log:
                raise RuntimeError(f"{name}: expected a Flux verification error")
            if not any(message in log.lower() for message in ("refinement type", "postcondition", "overflow", "underflow")):
                raise RuntimeError(f"{name}: failed without a recognized proof diagnostic")
            print(f"PASS: Flux rejected {name}", flush=True)


if __name__ == "__main__":
    main()
