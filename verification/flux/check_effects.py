#!/usr/bin/env python3
"""Check the effect-policy feasibility model, including unsound alternatives."""

import json
import os
from pathlib import Path
import re
import tempfile

from check import ROOT, TOOLCHAIN, run

SOURCE = ROOT / "verification/flux/effect_policy.rs"


def main():
    env = dict(os.environ, RUSTUP_TOOLCHAIN=TOOLCHAIN)
    with tempfile.TemporaryDirectory(prefix="wiggle-effects-") as directory:
        output = Path(directory)
        flags = ["--edition=2024", "--crate-type=lib", "--color=never", "--out-dir", str(output)]
        proof_flags = ["--cfg", "flux", "-Fcheck-overflow=strict", "-Fallow-raw-deref=none"]
        run(["rustc", *flags, str(SOURCE)], env=env, check=True)
        run(["flux", *flags, *proof_flags, str(SOURCE)], env=env, check=True)

        original = SOURCE.read_text().replace(
            '"../../crates/wiggle/src/bounds.rs"',
            json.dumps((ROOT / "crates/wiggle/src/bounds.rs").as_posix()),
        )
        mutations = {
            "wrong_memory_accepted": (
                "if owner != self.owner || memory != self.memory {",
                "if owner != self.owner {",
            ),
            "wrong_owner_accepted": (
                "if owner != self.owner || memory != self.memory {",
                "if memory != self.memory {",
            ),
            "unchecked_range": (
                "match bounds::checked_range_end(start, len, self.limit) {",
                "match Some(0usize) {",
            ),
            "unchecked_trace_append": (
                "fn(&mut SafeTrace[@p], SafeMemoryEffect{e:\n        e.owner == p.owner && e.memory == p.memory && e.limit == p.limit})",
                "fn(&mut SafeTrace[@p], SafeMemoryEffect)",
            ),
        }
        probes = {}
        for name, (before, after) in mutations.items():
            assert original.count(before) == 1, f"mutation anchor changed: {name}"
            probes[name] = original.replace(before, after)
        probes["foreign_trace"] = original + """
pub fn foreign_trace() {
    let policy = ModelPolicy::new(7, 11, 32);
    let mut other = SafeTrace::new(ModelPolicy::new(7, 12, 32));
    if let Some(effect) = policy.validate(7, 11, 0, 1, true) {
        other.append(effect);
    }
}
"""
        for name, source in probes.items():
            probe = output / f"{name}.rs"
            probe.write_text(source)
            run(["rustc", *flags, str(probe)], env=env, check=True)
            result = run(["flux", *flags, *proof_flags, str(probe)], env=env, capture_output=True)
            log = result.stdout + result.stderr
            print(log, flush=True)
            diagnostic = re.search(
                r"error\[E0999\]: (refinement type error|type invariant may not hold|arithmetic operation may (over|under)flow)",
                log,
            )
            if result.returncode == 0 or diagnostic is None:
                raise RuntimeError(f"{name}: expected a Flux proof diagnostic")
            print(f"PASS: Flux rejected effect probe {name}", flush=True)


if __name__ == "__main__":
    main()
