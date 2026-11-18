#!/usr/bin/env python3
"""Check iovec descriptor arithmetic without adding trusted specifications."""

import os
import re
import subprocess
from zipfile import ZipFile

from check_environment import DIAGNOSTIC, HERE, ROOT, TARGET, TOOLCHAIN


def check_source_anchors():
    wiggle = (ROOT / "crates/wiggle/src/lib.rs").read_text(encoding="utf-8")
    assert "(0..self.len()).map(move |i| base.add(i))" in wiggle
    assert re.search(r"amt\s*\.checked_mul\(T::guest_size\(\)\)\s*"
                     r"\.and_then\(\|o\| self.pointer.checked_add\(o\)\)", wiggle)
    with ZipFile(HERE / "evidence/run-44240968739/generated-glue.zip") as archive:
        expanded = archive.read("wasi-expanded.rs").decode("utf-8")
    p1 = next(m for m in re.finditer(r"pub async fn fd_read\s*\([^{}]+", expanded)
              if "WasiSnapshotPreview1" in m.group())
    reader = expanded[expanded.rindex("impl wiggle::GuestType for Iovec", 0, p1.start()):p1.start()]
    reader = reader[:reader.index("fn write(")]
    assert re.search(r"fn guest_size\(\) -> u32 \{ 8u32 \}", reader)
    assert re.search(r"fn guest_align\(\) -> usize \{ 4usize \}", reader)
    assert re.findall(r"location.cast::<u8>\(\).add\((\du32)\)\?\.cast\(\)", reader) == ["0u32", "4u32"]


def main():
    check_source_anchors()
    output = ROOT / "artifacts/fd-read/iovec-metadata"
    output.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, RUSTUP_TOOLCHAIN=TOOLCHAIN)
    env.pop("FLUX_DRIVER", None)
    env.pop("FLUX_COMPAT_RECEIPT", None)
    source = (HERE / "iovec_metadata.rs").read_text(encoding="utf-8")
    mutations = {
        "wrong_stride": ("index.checked_mul(IOVEC_STRIDE) else", "index.checked_mul(FIELD_BYTES) else"),
        "wrong_field": ("second as usize..end", "start as usize..end"),
        "missing_bounds": (" || end > len", ""),
    }
    cases = {"positive": source, "iterator_probe": source}
    for name, (old, new) in mutations.items():
        assert source.count(old) == 1, f"{name} mutation anchor changed"
        cases[name] = source.replace(old, new)
    for name, body in cases.items():
        path = output / f"{name}.rs"
        path.write_text(body, encoding="utf-8")
        flags = ["--edition=2024", "--crate-type=lib", "--target", TARGET,
                 "--color=never", "--out-dir", str(output), str(path)]
        if name == "iterator_probe":
            flags += ["--cfg", "iterator_probe"]
        for tool in ("rustc", "flux"):
            command = [tool, *flags]
            if tool == "flux":
                command += ["--cfg", "flux", "-Fcheck-overflow=strict",
                            "-Fallow-raw-deref=none", "-Fstd-extern-specs=on"]
            run = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True, timeout=120)
            log = run.stdout + run.stderr
            (output / f"{name}-{tool}.log").write_text(log, encoding="utf-8")
            print(f"{name}/{tool}: exit {run.returncode}\n{log}", flush=True)
            if tool == "rustc":
                if run.returncode:
                    return 1
                continue
            if re.search(r"internal (?:compiler|flux) error|panicked at", log, re.I):
                return 3
            if name == "iterator_probe" and run.returncode:
                if (not (DIAGNOSTIC.search(log) or "parameter inference error at function call" in log)
                        or "and_then" not in log or "unsupported" in log.lower()):
                    return 1
                continue
            if name in mutations:
                if not run.returncode or not DIAGNOSTIC.search(log) or "unsupported" in log.lower():
                    return 1
            else:
                expected = 3 if name == "iterator_probe" else 2
                if run.returncode or f"{expected} checked; 0 trusted; 0 ignored" not in log:
                    return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
