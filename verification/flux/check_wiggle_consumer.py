#!/usr/bin/env python3
"""Check that another crate can consume the original Wiggle size contract."""

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

from check_environment import ROOT, TARGET, TOOLCHAIN

SOURCE = """use wiggle::GuestType;

#[cfg_attr(flux, flux::sig(fn() -> u32[4]))]
pub fn width() -> u32 { u32::guest_size() }
"""


def main():
    artifacts = ROOT / "artifacts/fd-read"
    output = artifacts / "wiggle-consumer"
    output.mkdir(parents=True, exist_ok=True)
    mutations = json.loads((artifacts / "original-contract-mutations/contracts.json").read_text())
    checked = next(case for case in mutations["cases"] if case["name"] == "guest-size")
    report = {"scope": "Cross-crate use of the actual verified Wiggle integer size contract",
              "status": "open", "producer_mutation": checked, "runs": []}

    def save():
        (output / "consumer.json").write_text(json.dumps(report, indent=2) + "\n")

    save()
    if checked["status"] != "original-contract-checked-well-typed-body-mutation-rejected":
        print("Open: the original Wiggle size contract has no passing mutation evidence")
        return

    invocation = json.loads(
        (artifacts / "compat-original-body-probes/guest-size/compiler-invocation.json").read_text()
    )
    out_dir = Path(invocation[invocation.index("--out-dir") + 1])
    suffix, = [arg.split("=", 1)[1] for arg in invocation if arg.startswith("extra-filename=")]
    rmeta = out_dir / f"libwiggle{suffix}.rmeta"
    fluxmeta = rmeta.with_suffix(".fluxmeta")
    report["producer_artifacts"] = {
        str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in (rmeta, fluxmeta)
    }
    # Keep the Rust type identity and link search paths. Remove only the
    # adjacent Flux metadata for the negative control.
    plain = output / "without-flux-metadata"
    plain.mkdir(exist_ok=True)
    shutil.copyfile(rmeta, plain / rmeta.name)
    library_paths = [invocation[i + 1] for i, value in enumerate(invocation) if value == "-L"]
    rust_flags = ["--edition=2024", "--crate-type=lib", "--target", TARGET, "--color=never",
                  "--emit=metadata", "--out-dir", str(output)]
    for path in library_paths:
        rust_flags.extend(["-L", path])
    env = dict(os.environ, RUSTUP_TOOLCHAIN=TOOLCHAIN)
    for name, source, spec, expect_pass in (
        ("positive", SOURCE, rmeta, True),
        ("wrong-width", SOURCE.replace("u32[4]", "u32[5]"), rmeta, False),
        ("without-metadata", SOURCE, plain / rmeta.name, False),
    ):
        path = output / (name.replace("-", "_") + ".rs")
        path.write_text(source)
        for compiler in ("rustc", "flux"):
            command = [compiler, *rust_flags, "--extern", "wiggle=" + str(spec)]
            if compiler == "flux":
                command += ["--cfg", "flux", "-Fcheck-overflow=strict", "-Fallow-raw-deref=none",
                            "-Fstd-extern-specs=on", "-Flog-dir=" + str(output / "flux-log")]
            command.append(str(path))
            run = subprocess.run(command, cwd=ROOT, env=env, text=True, capture_output=True, timeout=120)
            log = run.stdout + run.stderr
            log_name = f"{name}-{compiler}.log"
            (output / log_name).write_text(log)
            report["runs"].append({"name": name, "command": command, "log": log_name, "exit_code": run.returncode})
            save()
            if compiler == "rustc" and run.returncode:
                raise RuntimeError("Consumer failed ordinary Rust compilation: " + log)
            if compiler == "flux":
                if expect_pass and (run.returncode or "1 checked; 0 trusted; 0 ignored" not in log):
                    raise RuntimeError("Consumer could not use the exported Wiggle contract: " + log)
                if not expect_pass and (not run.returncode or "error[E0999]: refinement type error" not in log):
                    raise RuntimeError("Consumer control did not fail refinement checking: " + log)
                if any(word in log for word in ("internal flux error", "internal compiler error", "unsupported")):
                    raise RuntimeError("A checker limitation is not a consumer result: " + log)
    report["status"] = "passed"
    save()
    print("PASS: downstream crate uses the original integer size contract and rejects both controls")


if __name__ == "__main__":
    main()
