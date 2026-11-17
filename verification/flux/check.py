#!/usr/bin/env python3
"""Check the production bounds helper and require Flux to reject mutations."""

import os
import json
import re
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
        flags = ["--edition=2024", "--crate-type=lib", "--color=never", "--out-dir", str(output)]
        proof_flags = ["--cfg", "flux", "-Fcheck-overflow=strict", "-Fallow-raw-deref=none"]
        run(["rustc", *flags, str(ROOT / "verification/flux/bounds.rs")], env=env, check=True)
        run(["flux", *flags, *proof_flags, str(ROOT / "verification/flux/bounds.rs")], env=env, check=True)

        original = SOURCE.read_text()
        harness = (ROOT / "verification/flux/bounds.rs").read_text()
        source_path = '"../../crates/wiggle/src/bounds.rs"'
        assert harness.count(source_path) == 1, "harness source path changed"
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
            mutant_harness = output / f"{name}_harness.rs"
            mutant_harness.write_text(harness.replace(source_path, json.dumps(mutant.as_posix())))
            # A syntax error or Rust compiler failure is not proof rejection.
            run(["rustc", *flags, str(mutant_harness)], env=env, check=True)
            result = run(["flux", *flags, *proof_flags, str(mutant_harness)], env=env, capture_output=True)
            log = result.stdout + result.stderr
            print(log, flush=True)
            # This pinned Flux revision uses rustc's E0999 diagnostic code.
            # Require an actual refinement/arithmetic failure, not a setup,
            # parsing, tool, or solver error that happens to exit nonzero.
            proof_error = re.search(
                r"error\[E0999\]: (refinement type error|arithmetic operation may (over|under)flow)",
                log,
            )
            if result.returncode == 0 or proof_error is None:
                raise RuntimeError(f"{name}: expected a Flux verification error")
            print(f"PASS: Flux rejected {name}", flush=True)


if __name__ == "__main__":
    main()
