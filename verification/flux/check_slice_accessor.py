#!/usr/bin/env python3
"""Try the accessor refactor in a full Wiggle source snapshot using baseline Flux."""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from probe_original import HERE, ROOT, TARGET


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--with-wasmtime", action="store_true")
    args = parser.parse_args()
    configuration = "wasmtime-enabled" if args.with_wasmtime else "slice-backed"
    suffix = "-wasmtime" if args.with_wasmtime else ""
    features = ["--features", "wasmtime"] if args.with_wasmtime else []
    output = ROOT / "artifacts/fd-read" / f"slice-accessor{suffix}"
    output.mkdir(parents=True, exist_ok=True)
    original = ROOT / "crates/wiggle"
    snapshot = output / "wiggle"
    shutil.copytree(original, snapshot, dirs_exist_ok=True)
    source = snapshot / "src/lib.rs"
    before = source.read_text(encoding="utf-8")
    anchor = "    pub fn as_slice_mut(&mut self, ptr: GuestPtr<[u8]>) -> Result<Option<&mut [u8]>, GuestError> {\n"
    old = anchor + "        let range = self.validate_range::<u8>(ptr.pointer.0, ptr.pointer.1)?;"
    assert before.count(old) == 1, "mutable-slice body changed"
    after = before.replace(old, anchor + "        let (offset, len) = ptr.slice_parts();\n        let range = self.validate_range::<u8>(offset, len)?;")
    after += """
impl GuestPtr<[u8]> {
    fn slice_parts(self) -> (u32, u32) {
        self.pointer
    }
}
"""
    source.write_text(after, encoding="utf-8")
    wrapper = output / "rustc-wrapper"
    wrapper.write_text(
        "#!/usr/bin/env python3\nimport sys\nsys.path.insert(0, " + repr(str(HERE)) + ")\n"
        "from probe_original import wrap\nsys.exit(wrap(sys.argv[1:]))\n",
        encoding="utf-8",
    )
    wrapper.chmod(0o755)
    env = dict(os.environ, CARGO_INCREMENTAL="0", CARGO_TERM_COLOR="never",
               RUSTUP_TOOLCHAIN="nightly-2026-10-22", RUSTC_WORKSPACE_WRAPPER=str(wrapper),
               FD_READ_PROBE_CRATE="wiggle", FD_READ_SOURCE_COPY=str(snapshot),
               FD_READ_PROBE_SELECTOR="def:as_slice_mut\ndef:slice_parts\ndef:validate_range",
               FD_READ_PROBE_OUTPUT=str(output))
    env.pop("FLUX_DRIVER", None)
    env.pop("FLUX_COMPAT_RECEIPT", None)
    report = {
        "scope": f"Refactored Wiggle snapshot ({configuration}); dependency bodies unchecked",
        "source_revision": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "original_sha256_lf": hashlib.sha256(before.encode()).hexdigest(),
        "snapshot_sha256_lf": hashlib.sha256(after.encode()).hexdigest(),
        "status": "open", "runs": [],
    }
    try:
        for mode in ("ordinary", "flux"):
            env["FD_READ_PROBE_MODE"] = mode
            command = ["cargo", "rustc", "--locked", "--target", TARGET, "-p", "wiggle",
                       "--no-default-features", *features, "--lib", "--", "--cfg",
                       f"fd_read_slice_accessor_{configuration.replace('-', '_')}_{mode}"]
            result = subprocess.run(command, cwd=ROOT, env=env, text=True, capture_output=True, timeout=900)
            log = result.stdout + result.stderr
            (output / f"{mode}.log").write_text(log, encoding="utf-8")
            report["runs"].append({"mode": mode, "command": command, "exit_code": result.returncode})
            for line in log.splitlines():
                if line.startswith(("error", "summary.")):
                    print(line, flush=True)
            if mode == "flux" and re.search(r"(?i)internal (?:compiler|flux) error|panicked at", log):
                report["status"] = "flux-crash"
                print("Flux crashed. Stopping for review with the trust boundary unchanged.", flush=True)
                return 3
            if result.returncode:
                report["status"] = f"{mode}-failed"
                return 1
        if not re.search(r"\b3 checked; \d+ trusted; 0 ignored\.", log):
            report["status"] = "unexpected-proof-coverage"
            return 1
        report["status"] = "accessor-slice-and-range-checked"
        return 0
    finally:
        (output / "result.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
