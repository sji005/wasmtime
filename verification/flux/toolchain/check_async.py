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
REFINED_TRAIT = TRAIT.replace(
    "pub trait Read { async fn",
    "pub trait Read {\n    #[cfg_attr(flux, flux::sig(async fn(&mut Self, usize[@n]) -> usize[n]))]\n    async fn",
)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, RUSTUP_TOOLCHAIN="nightly-2026-10-22")
    report = {"scope": "checker regression only; no WASI/async ownership theorem", "runs": []}
    sources = (("free", FREE), ("trait", TRAIT), ("rpit-trait", RPIT),
               ("nested-rpit-trait", NESTED), ("refined-trait", REFINED_TRAIT))
    for kind, source in sources:
        compatible = False
        for mutation in ("positive", "wrong-result", "weaker-impl") if kind == "refined-trait" else ("positive", "wrong-result"):
            name = kind + "-" + mutation
            expected_positive = mutation == "positive"
            path = OUT / (name.replace("-", "_") + ".rs")
            case_source = source if expected_positive else source.replace("{ n }", "{ 0 }")
            if mutation == "weaker-impl":
                # The mutated implementation body satisfies its own signature.
                # Its return contract is incompatible with the trait's identity.
                case_source = case_source.replace("fn(&mut Reader, usize[@n]) -> usize[n]", "fn(&mut Reader, usize) -> usize[0]")
            path.write_text(case_source)
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
                    if expected_positive:
                        compatible = result.returncode == 0 and "checked;" in log and "0 checked;" not in log
                        if not compatible:
                            report[kind + "_positive_diagnostic"] = "checker-limitation" if limitation else "unclassified"
                            print(log, flush=True)
                    elif compatible and (result.returncode == 0 or limitation or "error[E0999]:" not in log
                                         or not any(d in log for d in ("refinement type error", "incompatible refinement"))):
                        raise RuntimeError("Async negative control needs a refinement rejection: " + log)
                    if kind == "free" and (limitation or (expected_positive and not compatible)):
                        raise RuntimeError("Free async baseline regression failed: " + log)
        report[kind] = ("checked-with-rejected-well-typed-mutation" if compatible
                        else "open-" + report[kind + "_positive_diagnostic"])
    report["status"] = "classified"
    report["checker_variant"] = json.loads(Path(os.environ["FLUX_COMPAT_RECEIPT"]).read_text())
    (OUT / "async.json").write_text(json.dumps(report, indent=2) + "\n")
    print("Async compatibility: " + "; ".join(kind + "=" + report[kind] for kind, _ in sources))


if __name__ == "__main__":
    main()
