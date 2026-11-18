#!/usr/bin/env python3
"""Require explicit external Range Clone specs to preserve both endpoints."""

import json
import os
from pathlib import Path
import subprocess

from check_environment import ROOT, TARGET, TOOLCHAIN

SOURCE = '''use std::ops::Range;
#[cfg_attr(flux, flux::sig(fn(&Range<usize>[@r]) -> Range<usize>[r]))]
pub fn clone_range(r: &Range<usize>) -> Range<usize> { r.clone() }
'''


def main():
    output = ROOT / "artifacts/fd-read/clone-primitive-specs"
    output.mkdir(parents=True, exist_ok=True)
    primitive = json.loads(Path(os.environ["FD_READ_PRIMITIVE_MANIFEST"]).read_text())
    report = {"scope": "std clone primitive-spec regression only; not a Wasmtime body", "primitive": primitive, "runs": []}
    for name, source in (("positive", SOURCE), ("bad-endpoint", SOURCE.replace("Range<usize>[r]", "Range<usize>[Range { start: r.start, end: r.end + 1 }]"))):
        path = output / (name.replace("-", "_") + ".rs")
        path.write_text(source)
        for kind in ("rustc", "flux"):
            command = [kind, "--edition=2024", "--crate-type=lib", "--target", TARGET, "--color=never", "--out-dir", str(output)]
            if kind == "flux":
                command += ["--cfg", "flux", "-Fcheck-overflow=strict", "-Fallow-raw-deref=none", "-Fstd-extern-specs=on",
                            "-Flog-dir=" + str(output / "flux-log"), "-Zunstable-options"]
                for extension in ("rlib", "rmeta"):
                    command += ["--extern", "force:fd_read_file_primitive=" + primitive["artifacts"][extension]]
                command += ["-L", "dependency=" + str(Path(primitive["artifacts"]["rmeta"]).parent)]
            command.append(str(path))
            run = subprocess.run(command, cwd=ROOT, env=dict(os.environ, RUSTUP_TOOLCHAIN=TOOLCHAIN), text=True, capture_output=True, timeout=120)
            log = run.stdout + run.stderr
            filename = name + "-" + kind + ".log"
            (output / filename).write_text(log)
            report["runs"].append({"name": name, "kind": kind, "command": command, "exit_code": run.returncode, "log": filename})
            (output / "clone.json").write_text(json.dumps(report, indent=2) + "\n")
            if kind == "rustc" and run.returncode:
                raise RuntimeError("Clone regression is not well typed: " + log)
            if kind == "flux":
                if name == "positive" and (run.returncode or "1 checked; 0 trusted; 0 ignored" not in log):
                    raise RuntimeError("External clone relation was not preserved: " + log)
                if name != "positive" and (not run.returncode or "error[E0999]: refinement type error" not in log):
                    raise RuntimeError("Incorrect cloned endpoint was not rejected: " + log)
                if any(s in log for s in ("internal flux error", "internal compiler error", "unsupported")):
                    raise RuntimeError("Clone spec checker limitation: " + log)
    report["status"] = "passed"
    (output / "clone.json").write_text(json.dumps(report, indent=2) + "\n")
    print("PASS: cross-crate std Range Clone endpoint relation, incorrect endpoint rejected")


if __name__ == "__main__":
    main()
