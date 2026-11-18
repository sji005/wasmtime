#!/usr/bin/env python3
"""Mutation gates for original Wiggle pointer identities and range arithmetic.

The range bound is conditional on the two slice-backed variants; the binding's
Ranges variant, typed accesses and the fd_read theorem remain open.
Each experiment compiles a full temporary source snapshot using Cargo's actual
target, features, dependencies and manifest environment.
"""

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from check_environment import ROOT, HERE, TARGET, TOOLCHAIN

CASES = (
    ("pointer-array", "    pub fn as_array(&self", "GuestPtr::new((self.pointer, elems))", "GuestPtr::new((self.pointer, 0))"),
    ("pointer-base", "    pub fn offset_base(&self) -> u32", "self.pointer.0", "self.pointer.1"),
    ("pointer-len", "    pub fn len(&self) -> u32", "self.pointer.1", "self.pointer.0"),
    ("pointer-as-ptr", "    pub fn as_ptr(&self)", "GuestPtr::new(self.offset_base())", "GuestPtr::new(0)"),
    ("range", "    fn validate_range<T>", "let range = offset..offset + byte_len;", "let range = offset + 1..offset + byte_len;"),
    ("range-no-bounds-check", "    fn validate_range<T>", "if oob {", "if false {"),
)


def main():
    output = ROOT / "artifacts/fd-read/original-contract-mutations"
    output.mkdir(parents=True, exist_ok=True)
    positive = json.loads((ROOT / "artifacts/fd-read/compat-original-body-probes/original-body-probes.json").read_text())
    observed = {case["name"]: case for case in positive["cases"]}
    report = {"claim": "Pointer identities and slice-variant range contract only; binding's Ranges path, typed accesses and effects remain open",
              "positive": positive, "cases": [], "status": "open"}
    clone = json.loads((ROOT / "artifacts/fd-read/clone-primitive-specs/clone.json").read_text())
    source = ROOT / "crates/wiggle/src/lib.rs"
    original = source.read_text()
    for name, anchor, before, after in CASES:
        result_case = {"name": name, "runs": []}
        report["cases"].append(result_case)
        checked = observed["range" if name == "range-no-bounds-check" else name]
        if checked["source_sha256_lf"] != hashlib.sha256(original.encode()).hexdigest():
            raise RuntimeError("Proof and mutation source hashes differ")
        expected = ("conditional-slice-bound-checked-mutations-required" if name.startswith("range")
                    else "feasibility-only-no-spatial-postcondition")
        if checked["exit_code"] != 0 or checked["status"] != expected:
            result_case["status"] = "open-positive-contract-did-not-check"
            continue
        if name.startswith("range") and clone["status"] != "passed":
            result_case["status"] = "open-clone-contract-not-established"
            continue
        with tempfile.TemporaryDirectory(prefix=name + "-", dir=output) as temporary:
            copied = Path(temporary) / "wiggle"
            shutil.copytree(ROOT / "crates/wiggle", copied)
            start = original.index(anchor)
            # The selected methods have a single original expression of interest.
            # Restrict replacement to the selected method rather than another
            # identically named string accessor elsewhere in the original crate.
            end = original.index("\n    }", start) + len("\n    }")
            body = original[start:end]
            if body.count(before) != 1:
                raise RuntimeError("Mutation site changed or is ambiguous: " + name)
            mutated = original[:start] + body.replace(before, after) + original[end:]
            mutant = copied / "src/lib.rs"
            mutant.write_text(mutated)
            line = mutated[:mutated.index(anchor)].count("\n") + 1
            selector = f"span:{mutant.relative_to(ROOT).as_posix()}:{line}:5"
            case_dir = output / name
            case_dir.mkdir(exist_ok=True)
            wrapper = case_dir / "rustc-wrapper"
            wrapper.write_text("#!/usr/bin/env python3\nimport sys\nsys.path.insert(0, " + repr(str(HERE)) + ")\nfrom probe_original import wrap\nsys.exit(wrap(sys.argv[1:]))\n")
            wrapper.chmod(0o755)
            env = dict(os.environ, RUSTUP_TOOLCHAIN=TOOLCHAIN, CARGO_INCREMENTAL="0", CARGO_TERM_COLOR="never",
                       RUSTC_WORKSPACE_WRAPPER=str(wrapper), FD_READ_PROBE_CRATE="wiggle", FD_READ_SOURCE_COPY=str(copied),
                       FD_READ_PROBE_OUTPUT=str(case_dir), FD_READ_PROBE_SELECTOR=selector)
            for mode in ("ordinary", "flux"):
                env["FD_READ_PROBE_MODE"] = mode
                command = ["cargo", "rustc", "--locked", "--target", TARGET, "-p", "wiggle", "--all-features", "--lib", "--", "--cfg",
                           "fd_read_contract_mutant_" + name.replace("-", "_") + "_" + mode]
                run = subprocess.run(command, cwd=ROOT, env=env, text=True, capture_output=True, timeout=900)
                log = run.stdout + run.stderr
                (case_dir / (mode + ".log")).write_text(log)
                result_case["runs"].append({"mode": mode, "command": command, "exit_code": run.returncode})
                (output / "contracts.json").write_text(json.dumps(report, indent=2) + "\n")
                if mode == "ordinary" and run.returncode:
                    raise RuntimeError("Mutation is not well typed: " + name)
                if mode == "flux":
                    if run.returncode == 0 or "error[E0999]: refinement type error" not in log:
                        raise RuntimeError("Expected a refinement rejection of " + name)
                    if any(s in log for s in ("internal compiler error", "internal flux error", "unsupported", "timed out")):
                        raise RuntimeError("A checker limitation is not a mutation rejection: " + name)
            (case_dir / "mutated-lib.rs").write_text(mutated)
            result_case["mutation"] = {"before": before, "after": after, "source_sha256_lf": hashlib.sha256(mutated.encode()).hexdigest()}
            result_case["status"] = "original-contract-checked-well-typed-body-mutation-rejected"
            print(name + ": " + result_case["status"], flush=True)
    report["status"] = "classified"
    (output / "contracts.json").write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
