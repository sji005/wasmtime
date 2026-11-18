#!/usr/bin/env python3
"""Isolate native async trait compatibility without changing any WASI body."""

import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "artifacts/fd-read/compat-async"
FREE = '''#![allow(dead_code)]
#[cfg(flux)] extern crate flux_core;
#[cfg_attr(flux, flux::sig(async fn(usize[@n]) -> usize[n]))]
pub async fn identity(n: usize) -> usize { n }
'''
TRAIT = '''#![allow(dead_code, async_fn_in_trait)]
#[cfg(flux)] extern crate flux_core;
pub trait Read { async fn read(&mut self, n: usize) -> usize; }
pub struct Reader;
impl Read for Reader {
    #[cfg_attr(flux, flux::sig(async fn(&mut Reader, usize[@n]) -> usize[n]))]
    async fn read(&mut self, n: usize) -> usize { n }
}
'''
RPIT = TRAIT.replace("async fn read(&mut self, n: usize) -> usize;",
                     "fn read(&mut self, n: usize) -> impl std::future::Future<Output = usize> + Send;")
NESTED = RPIT.replace("-> usize { n }", "-> usize { async move { n }.await }")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, RUSTUP_TOOLCHAIN="nightly-2026-10-22")
    report = {"scope": "checker regression only; no WASI/async ownership theorem", "runs": []}
    for kind, source in (("free", FREE), ("trait", TRAIT), ("rpit-trait", RPIT), ("nested-rpit-trait", NESTED)):
        compatible = False
        for mutation in (False, True):
            name = kind + ("-wrong-result" if mutation else "-positive")
            path = OUT / (name.replace("-", "_") + ".rs")
            path.write_text(source.replace("{ n }", "{ 0 }") if mutation else source)
            flags = ["--edition=2024", "--crate-type=lib", "--color=never", "--out-dir", str(OUT)]
            for compiler in ("rustc", "flux"):
                command = [compiler, *flags]
                if compiler == "flux":
                    command += ["--cfg", "flux", "-Fcheck-overflow=strict", "-Fallow-raw-deref=none",
                                "-Flog-dir=" + str(OUT / "flux-log")]
                command.append(str(path))
                result = subprocess.run(command, cwd=ROOT, env=env, text=True, capture_output=True, timeout=120)
                log = result.stdout + result.stderr
                log_name = name + "-" + compiler + ".log"
                (OUT / log_name).write_text(log)
                report["runs"].append({"name": name, "compiler": compiler, "command": command,
                                       "exit_code": result.returncode, "log": log_name})
                (OUT / "async.json").write_text(json.dumps(report, indent=2) + "\n")
                if compiler == "rustc" and result.returncode:
                    raise RuntimeError("Async regression is not well typed: " + log)
                if compiler == "flux":
                    limitation = any(s in log for s in ("internal flux error", "internal compiler error", "unsupported", "not supported"))
                    if not mutation:
                        compatible = result.returncode == 0 and "checked;" in log and "0 checked;" not in log
                        if not compatible and not limitation:
                            raise RuntimeError("Unclassified async regression: " + log)
                    elif compatible and (result.returncode == 0 or limitation or "error[E0999]: refinement type error" not in log):
                        raise RuntimeError("Async wrong-result mutation was not rejected for refinement reasons: " + log)
                    if kind == "free" and (limitation or (not mutation and not compatible)):
                        raise RuntimeError("Free async baseline regression failed: " + log)
        report[kind] = "checked-with-rejected-well-typed-mutation" if compatible else "open-checker-limitation"
    report["status"] = "classified"
    report["checker_variant"] = json.loads(Path(os.environ["FLUX_COMPAT_RECEIPT"]).read_text())
    (OUT / "async.json").write_text(json.dumps(report, indent=2) + "\n")
    print("Async compatibility: " + "; ".join(kind + "=" + report[kind] for kind in ("free", "trait", "rpit-trait", "nested-rpit-trait")))


if __name__ == "__main__":
    main()
