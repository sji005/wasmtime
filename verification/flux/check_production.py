#!/usr/bin/env python3
"""Prove the production WAVE memory policy, real-pointer permits and consumers."""

import json
import os
from pathlib import Path
import re
import tempfile

from check import ROOT, TOOLCHAIN, run


def main():
    env = dict(os.environ, RUSTUP_TOOLCHAIN=TOOLCHAIN)
    policy = ROOT / "crates/wiggle/src/memory_policy.rs"
    harness = ROOT / "verification/flux/production_memory.rs"
    with tempfile.TemporaryDirectory(prefix="wave-production-") as directory:
        output = Path(directory)
        flags = ["--edition=2024", "--crate-type=lib", "--color=never", "--out-dir", str(output)]
        proof = ["--cfg", "flux", "-Fcheck-overflow=strict", "-Fallow-raw-deref=none"]
        run(["flux", *flags, *proof, str(harness)], env=env, check=True)
        original = policy.read_text()
        probes = {
            "unchecked_offset": (
                "checked_range_end(start, count, self.len)?;",
                "let _ = (start, count);",
                2,
            ),
            "null_root": (
                "let root = memory.as_mut_ptr();",
                "let root = std::ptr::null_mut();",
                1,
            ),
            "foreign_allocation": (
                "let pointer = unsafe { self.root.add(start) };",
                "let mut foreign = [0u8; 1]; let pointer = foreign.as_mut_ptr();",
                1,
            ),
            "oversized_copy": (
                "std::ptr::copy(source.as_ptr(), self.pointer, self.count)",
                "std::ptr::copy(source.as_ptr(), self.pointer, source.len() + 1)",
                1,
            ),
            "oversized_syscall": (
                "os_read_at(file, self.pointer, self.count, offset)",
                "os_read_at(file, self.pointer, self.count + 1, offset)",
                1,
            ),
        }
        for name, (before, after, count) in probes.items():
            assert original.count(before) == count, f"mutation anchor changed: {name}"
            mutant = output / f"{name}.rs"
            mutant.write_text(original.replace(before, after))
            root = output / f"{name}_harness.rs"
            root.write_text(
                "#[cfg(flux)] extern crate flux_core;\n"
                + "#[path = " + json.dumps((ROOT / "crates/wiggle/src/bounds.rs").as_posix()) + "] mod bounds;\n"
                + "#[path = " + json.dumps(mutant.as_posix()) + "] mod memory_policy;\n"
            )
            run(["rustc", *flags, str(root)], env=env, check=True)
            result = run(["flux", *flags, *proof, str(root)], env=env, capture_output=True)
            log = result.stdout + result.stderr
            print(log, flush=True)
            diagnostic = re.search(
                r"error\[E0999\]: (refinement type error|type invariant may not hold|arithmetic operation may (over|under)flow)",
                log,
            )
            if result.returncode == 0 or diagnostic is None:
                raise RuntimeError(f"{name}: expected a Flux proof diagnostic")
            print(f"PASS: Flux rejected production memory probe {name}", flush=True)


if __name__ == "__main__":
    main()
