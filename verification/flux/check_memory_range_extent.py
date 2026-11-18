#!/usr/bin/env python3
"""Check isolated range arithmetic under the existing allocation assumption."""

import json
import os
from pathlib import Path
import re
import subprocess

from check_environment import DIAGNOSTIC, HERE, ROOT, TARGET, TOOLCHAIN


def main():
    output = ROOT / "artifacts/fd-read/memory-range-extent"
    output.mkdir(parents=True, exist_ok=True)
    primitive = json.loads(Path(os.environ["FD_READ_PRIMITIVE_MANIFEST"]).read_text())
    env = dict(os.environ, RUSTUP_TOOLCHAIN=TOOLCHAIN)
    env.pop("FLUX_DRIVER", None)
    env.pop("FLUX_COMPAT_RECEIPT", None)
    original = (HERE / "memory_range_extent.rs").read_text()
    mutations = {
        "weakened_guard": ("range.end > len", "range.start > len"),
        "wrong_width": ("), width))", "), 0))"),
        "unchecked_caller": (" requires r.start <= r.end && r.end <= len", ""),
        "unrelated_snapshot_length": ("flux::field(usize[extent])", "flux::field(usize)"),
    }
    cases = {"positive": original}
    for name, (before, after) in mutations.items():
        assert original.count(before) == 1, f"{name} mutation anchor changed"
        cases[name] = original.replace(before, after)
    probes = {
        "provenance_probe": "core::ptr::with_exposed_provenance_mut(addr)",
        "constructor_probe": "std::slice::from_raw_parts_mut(start, width)",
    }
    cases.update(dict.fromkeys(probes, original))
    for name, source in cases.items():
        path = output / f"{name}.rs"
        path.write_text(source)
        flags = ["--edition=2024", "--crate-type=lib", "--target", TARGET,
                 "--color=never", "--out-dir", str(output), str(path)]
        if name in probes:
            flags += ["--cfg", name]
        for tool in ("rustc", "flux"):
            command = [tool, *flags]
            if tool == "flux":
                command.extend(["--cfg", "flux", "-Fcheck-overflow=strict",
                                "-Fallow-raw-deref=none", "-Fstd-extern-specs=on", "-Zunstable-options"])
                for kind in ("rmeta", "rlib"):
                    command += ["--extern", "force:fd_read_file_primitive=" + primitive["artifacts"][kind]]
                command += ["-L", "dependency=" + str(Path(primitive["artifacts"]["rmeta"]).parent)]
            run = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True, timeout=120)
            log = run.stdout + run.stderr
            (output / f"{name}-{tool}.log").write_text(log)
            print(f"{name}/{tool}: exit {run.returncode}\n{log}", flush=True)
            if tool == "rustc" and run.returncode:
                return 1
            if tool == "flux":
                if re.search(r"internal (?:compiler|flux) error|panicked at", log, re.I):
                    return 3
                if name == "positive" and (run.returncode or "3 checked; 0 trusted; 0 ignored" not in log):
                    return 1
                if name in probes:
                    if not run.returncode:
                        if "4 checked; 0 trusted; 0 ignored" not in log:
                            return 1
                        print(f"{name}: postcondition checked with existing specifications.", flush=True)
                    else:
                        if (not DIAGNOSTIC.search(log) or "a postcondition cannot be proved" not in log
                                or probes[name] not in log or "unsupported" in log.lower()):
                            return 1
                        print(f"{name}: postcondition remains unproved with existing specifications.", flush=True)
                elif name in mutations and (not run.returncode or not DIAGNOSTIC.search(log) or "unsupported" in log.lower()):
                    return 1
                if name == "unchecked_caller" and "a precondition cannot be proved" not in log:
                    return 1
                if name == "unrelated_snapshot_length" and "validated_range_width(base, len, range)" not in log:
                    return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
