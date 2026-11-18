#!/usr/bin/env python3
"""Require the original full-crate adapter contract and a rejected source mutation.

The negative experiment uses a complete temporary copy of the WASI crate source,
the same actual dependencies, manifest environment, target and feature set, and
the same external primitive spec. No production source is modified in place.
"""

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from check_environment import ROOT, HERE, TARGET, TOOLCHAIN


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    output = ROOT / "artifacts/fd-read/adapter-original-mutation"
    output.mkdir(parents=True, exist_ok=True)
    positive_dir = ROOT / "artifacts/fd-read/compat-adapter-original"
    positive = json.loads((positive_dir / "original-body-probes.json").read_text())
    case, = positive["cases"]
    if case["name"] != "unix-read-adapter" or case["exit_code"] != 0 or case["status"] != "feasibility-only-no-spatial-postcondition":
        raise RuntimeError("Original full-crate adapter did not check; no mutation result can discharge it")
    source = ROOT / case["source"]
    if case["source_sha256_lf"] != sha(source.read_text().encode()):
        raise RuntimeError("Original proof and mutation input sources differ")
    if positive["external_file_primitive"] is None:
        raise RuntimeError("Missing explicit external File primitive specification")
    report = {
        "claim": "Original Unix forwarding adapter's success-count contract only; fd_read callers and heap effects remain open",
        "positive": positive,
        "checker_variant": json.loads(Path(os.environ["FLUX_COMPAT_RECEIPT"]).read_text()),
        "mutation": "Replace only file.read_at(buf, pos) with Ok(usize::MAX) in a temporary full-source copy",
        "status": "open",
        "runs": [],
    }
    with tempfile.TemporaryDirectory(prefix="source-", dir=output) as temporary:
        copied = Path(temporary) / "wasi"
        shutil.copytree(ROOT / "crates/wasi", copied)
        mutant = copied / "src/filesystem/unix.rs"
        original = mutant.read_text()
        before = "    file.read_at(buf, pos)\n"
        if original.count(before) != 1:
            raise RuntimeError("Mutation anchor is ambiguous")
        mutated = original.replace(before, "    Ok(usize::MAX)\n")
        mutant.write_text(mutated)
        report["original_source_sha256_lf"] = sha(original.encode())
        report["mutated_source_sha256_lf"] = sha(mutated.encode())
        anchor = "pub(crate) fn read_at_cursor_unspecified("
        line = mutated[:mutated.index(anchor)].count("\n") + 1
        selector = f"span:{mutant.relative_to(ROOT).as_posix()}:{line}:1"
        wrapper = output / "rustc-wrapper"
        wrapper.write_text("#!/usr/bin/env python3\nimport sys\nsys.path.insert(0, " + repr(str(HERE)) + ")\nfrom probe_original import wrap\nsys.exit(wrap(sys.argv[1:]))\n")
        wrapper.chmod(0o755)
        env = dict(os.environ, RUSTUP_TOOLCHAIN=TOOLCHAIN, CARGO_INCREMENTAL="0", CARGO_TERM_COLOR="never",
                   RUSTC_WORKSPACE_WRAPPER=str(wrapper), FD_READ_PROBE_CRATE="wasmtime_wasi",
                   FD_READ_PROBE_OUTPUT=str(output), FD_READ_PROBE_SELECTOR=selector, FD_READ_SOURCE_COPY=str(copied))
        base = ["cargo", "rustc", "--locked", "--target", TARGET, "-p", "wasmtime-wasi", "--no-default-features", "--features", "p1", "--lib", "--", "--cfg"]
        for mode in ("ordinary", "flux"):
            env["FD_READ_PROBE_MODE"] = mode
            command = [*base, "fd_read_adapter_mutant_" + mode]
            result = subprocess.run(command, cwd=ROOT, env=env, text=True, capture_output=True, timeout=900)
            log = result.stdout + result.stderr
            (output / f"mutant-{mode}.log").write_text(log)
            report["runs"].append({"mode": mode, "command": command, "exit_code": result.returncode})
            (output / "adapter-original.json").write_text(json.dumps(report, indent=2) + "\n")
            if mode == "ordinary" and result.returncode:
                raise RuntimeError("The mutated original source did not compile as Rust")
            if mode == "flux":
                if result.returncode == 0 or "error[E0999]: refinement type error" not in log:
                    raise RuntimeError("Expected a real refinement rejection of the mutated original adapter")
                if any(word in log for word in ("internal compiler error", "internal flux error", "unsupported", "timed out")):
                    raise RuntimeError("A checker limitation is not a mutation rejection")
        archive = shutil.make_archive(str(output / "mutated-wasi-source"), "zip", temporary, "wasi")
        report["mutated_source_archive_sha256"] = sha(Path(archive).read_bytes())
    report["status"] = "original-count-contract-checked-and-mutant-rejected"
    (output / "adapter-original.json").write_text(json.dumps(report, indent=2) + "\n")
    print("PASS: actual full-crate Unix adapter count contract; well-typed original-body mutation rejected; fd_read still open")


if __name__ == "__main__":
    main()
