#!/usr/bin/env python3
"""Compile explicit std File and Range primitive contracts."""

import json
import os
from pathlib import Path
import subprocess

from check_environment import ROOT, HERE, TARGET, TOOLCHAIN


def main():
    output = ROOT / "artifacts/fd-read/file-primitive-specs"
    output.mkdir(parents=True, exist_ok=True)
    command = [
        "flux", "--crate-name", "fd_read_file_primitive", "--edition=2024", "--crate-type=lib",
        "--target", TARGET, "--emit=metadata,link", "--out-dir", str(output),
        "--cfg", "flux", "-Ffull-compilation=on", "-Fstd-extern-specs=on",
        "-Fcheck-overflow=strict", "-Fallow-raw-deref=none",
        "-Flog-dir=" + str(output / "flux-log"), str(HERE / "file_read_specs.rs"),
    ]
    result = subprocess.run(command, cwd=ROOT, env=dict(os.environ, RUSTUP_TOOLCHAIN=TOOLCHAIN), text=True, capture_output=True, timeout=120)
    (output / "compile.log").write_text(result.stdout + result.stderr)
    print(result.stdout + result.stderr, flush=True)
    if result.returncode:
        raise RuntimeError("External primitive specification did not compile")
    artifacts = {}
    for kind in ("rlib", "rmeta", "fluxmeta"):
        paths = list(output.glob("*." + kind))
        if len(paths) != 1:
            raise RuntimeError(f"Expected one primitive-spec {kind} artifact: {paths}")
        artifacts[kind] = str(paths[0])
    manifest = output / "extern-specs.json"
    manifest.write_text(json.dumps({
        "command": command,
        "artifacts": artifacts,
        "trusted": [
            "std FileExt::read_at for File",
            "usize identity Clone and Range<Idx> fieldwise Clone preserving Idx::cloned",
            "ExactSizeIterator::len for Range<usize>",
        ],
    }, indent=2) + "\n")
    with Path(os.environ["GITHUB_ENV"]).open("a") as env_file:
        env_file.write("FD_READ_PRIMITIVE_MANIFEST=" + str(manifest) + "\n")


if __name__ == "__main__":
    main()
