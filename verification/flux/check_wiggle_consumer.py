#!/usr/bin/env python3
"""Use Cargo's real dependency invocation to test checked Wiggle metadata."""

import json
import os
from pathlib import Path
import shutil
import subprocess

from check_environment import HERE, ROOT, TARGET, TOOLCHAIN

SOURCE = """use wiggle::GuestType;

#[cfg_attr(flux, flux::sig(fn() -> u32[4]))]
pub fn width() -> u32 { u32::guest_size() }
"""
FLAGS = ["-Fcheck-overflow=strict", "-Fallow-raw-deref=none", "-Fstd-extern-specs=on",
         "-Ffull-compilation=on", "-Ffixpoint-timeout=30"]


def wrap(args):
    compiler, *rustargs = args
    crate = rustargs[rustargs.index("--crate-name") + 1] if "--crate-name" in rustargs else None
    mode = os.environ["FD_READ_CONSUMER_MODE"]
    output = Path(os.environ["FD_READ_CONSUMER_OUTPUT"])
    selected = {"fd_read_wiggle_consumer"}
    if mode == "with-metadata":
        selected.add("wiggle")
    command = [compiler, *rustargs]
    if crate in selected:
        command = ["flux", *rustargs, *FLAGS, "-Flog-dir=" + str(output / (crate + "-flux-log"))]
        if crate == "wiggle":
            command.append("-Finclude=def:>::guest_size")
    if crate in ("wiggle", "fd_read_wiggle_consumer"):
        (output / (crate + "-invocation.json")).write_text(json.dumps(command, indent=2) + "\n")
    return subprocess.run(command, close_fds=False).returncode


def main():
    artifacts = ROOT / "artifacts/fd-read"
    output = artifacts / "wiggle-consumer"
    output.mkdir(parents=True, exist_ok=True)
    project = output / "project"
    source_path = project / "src/lib.rs"
    source_path.parent.mkdir(parents=True, exist_ok=True)
    wiggle = json.dumps(str(ROOT / "crates/wiggle"))
    (project / "Cargo.toml").write_text(f"""[package]
name = "fd-read-wiggle-consumer"
version = "0.0.0"
edition = "2024"

[dependencies]
wiggle = {{ path = {wiggle}, default-features = false }}

[workspace]
""")
    shutil.copyfile(ROOT / "Cargo.lock", project / "Cargo.lock")
    wrapper = output / "rustc-wrapper"
    wrapper.write_text("#!/usr/bin/env python3\nimport sys\nsys.path.insert(0, " + repr(str(HERE)) +
                       ")\nfrom check_wiggle_consumer import wrap\nsys.exit(wrap(sys.argv[1:]))\n")
    wrapper.chmod(0o755)
    base = ["cargo", "check", "--offline", "--target", TARGET, "--lib"]
    env = dict(os.environ, RUSTUP_TOOLCHAIN=TOOLCHAIN, CARGO_TERM_COLOR="never", CARGO_INCREMENTAL="0")
    report = {"scope": "Use of the original scoped Wiggle size proof in a Cargo consumer", "status": "open", "runs": []}
    for name, source, mode, passes in (
        ("ordinary", SOURCE, "ordinary", True),
        ("positive", SOURCE, "with-metadata", True),
        ("wrong-width", SOURCE.replace("u32[4]", "u32[5]"), "with-metadata", False),
        ("without-metadata", SOURCE, "without-metadata", False),
    ):
        source_path.write_text(source)
        case = output / name
        case.mkdir(exist_ok=True)
        (case / "consumer.rs").write_text(source)
        case_env = dict(env, CARGO_TARGET_DIR=str(ROOT / "target/fd-read-wiggle-consumer" / mode))
        command = [*base]
        if mode != "ordinary":
            command.append("--locked")
            case_env.update(RUSTC_WRAPPER=str(wrapper), FD_READ_CONSUMER_MODE=mode,
                            FD_READ_CONSUMER_OUTPUT=str(case))
        run = subprocess.run(command, cwd=project, env=case_env, text=True, capture_output=True, timeout=900)
        log = run.stdout + run.stderr
        (case / "compile.log").write_text(log)
        report["runs"].append({"name": name, "command": command, "exit_code": run.returncode})
        (output / "consumer.json").write_text(json.dumps(report, indent=2) + "\n")
        if passes and run.returncode:
            raise RuntimeError("Consumer compilation failed in " + name + ": " + log[-6000:])
        if name == "positive":
            if "12 checked;" not in log or "1 checked; 0 trusted; 0 ignored" not in log:
                raise RuntimeError("Expected both the original Wiggle and consumer body checks")
        if not passes and (not run.returncode or "error[E0999]: refinement type error" not in log):
            raise RuntimeError("Consumer control did not fail refinement checking: " + log[-6000:])
        if any(word in log for word in ("internal flux error", "internal compiler error", "unsupported")):
            raise RuntimeError("A checker limitation is not a consumer result: " + log[-6000:])
    report["status"] = "passed"
    (output / "consumer.json").write_text(json.dumps(report, indent=2) + "\n")
    print("PASS: Cargo consumer uses the original Wiggle size contract and rejects both controls")


if __name__ == "__main__":
    main()
