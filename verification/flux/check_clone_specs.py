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
LENGTH = '''use std::ops::Range;
#[cfg_attr(flux, flux::sig(fn(&Range<usize>[@r]) -> usize[if r.start <= r.end { r.end - r.start } else { 0 }]))]
pub fn range_length(r: &Range<usize>) -> usize { r.len() }
'''


def main():
    output = ROOT / "artifacts/fd-read/clone-primitive-specs"
    output.mkdir(parents=True, exist_ok=True)
    primitive = json.loads(Path(os.environ["FD_READ_PRIMITIVE_MANIFEST"]).read_text())
    report = {"scope": "std range primitive-spec regressions", "primitive": primitive, "runs": []}
    cases = (
        ("clone", True, SOURCE),
        ("clone", False, SOURCE.replace("Range<usize>[r]", "Range<usize>[Range { start: r.start, end: r.end + 1 }]")),
        ("length", True, LENGTH),
        ("length", False, LENGTH.replace("r.end - r.start", "r.end - r.start + 1")),
    )
    checked = {}
    for kind, expected_positive, source in cases:
        name = kind + ("-positive" if expected_positive else "-wrong-result")
        path = output / (name.replace("-", "_") + ".rs")
        path.write_text(source)
        for compiler in ("rustc", "flux"):
            command = [compiler, "--edition=2024", "--crate-type=lib", "--target", TARGET, "--color=never", "--out-dir", str(output)]
            if compiler == "flux":
                command += ["--cfg", "flux", "-Fcheck-overflow=strict", "-Fallow-raw-deref=none", "-Fstd-extern-specs=on",
                            "-Flog-dir=" + str(output / "flux-log"), "-Zunstable-options"]
                for extension in ("rlib", "rmeta"):
                    command += ["--extern", "force:fd_read_file_primitive=" + primitive["artifacts"][extension]]
                command += ["-L", "dependency=" + str(Path(primitive["artifacts"]["rmeta"]).parent)]
            command.append(str(path))
            run = subprocess.run(command, cwd=ROOT, env=dict(os.environ, RUSTUP_TOOLCHAIN=TOOLCHAIN), text=True, capture_output=True, timeout=120)
            log = run.stdout + run.stderr
            filename = name + "-" + compiler + ".log"
            (output / filename).write_text(log)
            report["runs"].append({"name": name, "compiler": compiler, "command": command, "exit_code": run.returncode, "log": filename})
            (output / "clone.json").write_text(json.dumps(report, indent=2) + "\n")
            if compiler == "rustc" and run.returncode:
                raise RuntimeError("Range regression is not well typed: " + log)
            if compiler == "flux":
                if expected_positive:
                    checked[kind] = run.returncode == 0 and "1 checked; 0 trusted; 0 ignored" in log
                if checked[kind] and not expected_positive and (not run.returncode or "error[E0999]: refinement type error" not in log):
                    raise RuntimeError("Incorrect range result was not rejected: " + log)
                if checked[kind] and any(s in log for s in ("internal flux error", "internal compiler error", "unsupported")):
                    raise RuntimeError("Range spec checker limitation: " + log)
                if not checked[kind]:
                    print(log, flush=True)
    report["status"] = "passed" if checked["clone"] else "open-clone-contract-not-established"
    report["length_status"] = "passed" if checked["length"] else "open-length-contract-not-established"
    (output / "clone.json").write_text(json.dumps(report, indent=2) + "\n")
    print("Cross-crate std Range Clone endpoint relation: " + report["status"])
    print("Cross-crate std Range length relation: " + report["length_status"])


if __name__ == "__main__":
    main()
