#!/usr/bin/env python3
"""Compare baseline/candidate selection; require selected bad accesses rejected.

Excluded functions are deliberately unsafe and are not claimed verified. The
regression checks that span selection targets exactly one function, including
when unrelated opaque lifetimes or external macro definitions are present.
"""

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "artifacts/fd-read/compat-selection"
COMMON = "#![allow(dead_code)]\n#[cfg(flux)] extern crate flux_core;\n"
SELECTED = "#[cfg_attr(flux, flux::sig(fn(bytes: &[u8][@n], index: usize{index < n}) -> u8))]\npub fn selected(bytes: &[u8], index: usize) -> u8 { bytes[index] }\n"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    candidate = os.environ["FLUX_DRIVER"]
    report = {"scope": "selection regression, not proof of excluded functions", "candidate": candidate, "runs": []}
    flags = ["--edition=2024", "--crate-type=lib", "--color=never", "--out-dir", str(OUT)]
    proof = ["--cfg", "flux", "-Fcheck-overflow=strict", "-Fallow-raw-deref=none", "-Flog-dir=" + str(OUT / "flux-log")]

    def run(name, command, env):
        result = subprocess.run(command, cwd=ROOT, env=env, text=True, capture_output=True, timeout=120)
        log = result.stdout + result.stderr
        (OUT / f"{name}.log").write_text(log)
        report["runs"].append({"name": name, "command": command, "exit_code": result.returncode, "log": f"{name}.log"})
        (OUT / "selection.json").write_text(json.dumps(report, indent=2) + "\n")
        return result.returncode, log

    env = dict(os.environ, RUSTUP_TOOLCHAIN="nightly-2026-10-22")
    # Definition is outside the checked working directory, like bitflags in the
    # Cargo registry; its expansion call site is in our local harness.
    with tempfile.TemporaryDirectory(prefix="fd-read-foreign-macro-") as tmp:
        macro_source = Path(tmp) / "foreign_macro.rs"
        macro_text = '#[macro_export] macro_rules! unrelated { () => { pub fn outside(bytes: &[u8]) -> u8 { bytes[bytes.len()] } }; }\n'
        macro_source.write_text(macro_text)
        (OUT / "foreign_macro.rs").write_text(macro_text)
        code, log = run("macro-rustc", ["rustc", *flags, str(macro_source)], env)
        if code:
            raise RuntimeError(log)
        cases = {
            "opaque": COMMON + "struct Counter { len: u32 }\nimpl Counter {\n    fn iter(&self) -> impl ExactSizeIterator<Item = u32> + '_ {\n        (0..self.len).map(move |i| i)\n    }\n}\n" + SELECTED,
            "macro": COMMON + "extern crate foreign_macro;\nforeign_macro::unrelated!();\n" + SELECTED,
        }
        for name, source in cases.items():
            for mutant in (False, True):
                label = name + ("-bad-selected" if mutant else "-positive")
                text = source.replace("{ bytes[index] }", "{ bytes[bytes.len()] }") if mutant else source
                path = OUT / (label.replace("-", "_") + ".rs")
                path.write_text(text)
                extra = ["--extern", "foreign_macro=" + str(OUT / "libforeign_macro.rlib")] if name == "macro" else []
                code, log = run(label + "-rustc", ["rustc", *flags, *extra, str(path)], env)
                if code:
                    raise RuntimeError("Ordinary compilation failed: " + log)
                line = text[:text.index("pub fn selected")].count("\n") + 1
                selector = f"-Finclude=span:{path.relative_to(ROOT).as_posix()}:{line}:1"
                command = ["flux", *flags, *extra, *proof, selector, str(path)]
                baseline = dict(env)
                baseline.pop("FLUX_DRIVER", None)
                baseline.pop("FLUX_COMPAT_RECEIPT", None)
                # Preserve baseline behavior, but only the candidate is a gate.
                if not mutant:
                    run(label + "-baseline", command, baseline)
                code, log = run(label + "-candidate", command, env)
                if mutant:
                    if code == 0 or "error[E0999]: assertion might fail: possible out-of-bounds access" not in log:
                        raise RuntimeError("Selected bad access was not rejected: " + log)
                elif code or not re.search(r"1 checked; 1 trusted; 0 ignored", log):
                    raise RuntimeError("Expected exactly selected checked body and one excluded body: " + log)
                if "internal compiler error" in log:
                    raise RuntimeError("Candidate checker crashed")
                print(f"PASS: {label}; excluded body remains unverified", flush=True)
    report["status"] = "passed"
    report["patch_sha256"] = hashlib.sha256((Path(__file__).parent / "include-selection.patch").read_bytes()).hexdigest()
    (OUT / "selection.json").write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
