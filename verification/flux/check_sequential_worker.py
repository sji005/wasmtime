"""Probe the synchronous worker with baseline Flux; never use FLUX_DRIVER overrides.

Run compile_primitive_specs.py and check_environment.py using the unmodified
pinned installation first. FD_READ_PRIMITIVE_MANIFEST selects the existing OS
primitive specifications; no new trusted local wrapper is introduced.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess

from check_environment import ROOT, HERE, TARGET, TOOLCHAIN, DIAGNOSTIC


def main():
    output = ROOT / "artifacts/fd-read/sequential-worker"
    output.mkdir(parents=True, exist_ok=True)
    source = HERE / "sequential_worker.rs"
    env = dict(os.environ, RUSTUP_TOOLCHAIN=TOOLCHAIN)
    env.pop("FLUX_DRIVER", None)
    env.pop("FLUX_COMPAT_RECEIPT", None)
    primitive = json.loads(Path(env["FD_READ_PRIMITIVE_MANIFEST"]).read_text())
    report = {
        "claim": "Sequential worker buffer length only; no original hostcall or scheduling theorem",
        "checker": "Default installed Flux driver; compatibility overrides removed. Requires baseline installation provenance.",
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "runs": [], "status": "open",
    }
    positive = source.read_text()
    # Use a well-typed body mutation that violates the stated length bound.
    negative = positive.replace("    Ok(buffer)\n", "    buffer.push(0);\n    Ok(buffer)\n")
    assert negative != positive
    try:
        for name, text in (("positive", positive), ("extra-byte", negative)):
            path = output / (name.replace("-", "_") + ".rs")
            path.write_text(text)
            for tool in ("rustc", "flux"):
                command = [tool, "--edition=2024", "--crate-type=lib", "--target", TARGET,
                           "--color=never", "--out-dir", str(output)]
                if tool == "flux":
                    command += ["--cfg", "flux", "-Fcheck-overflow=strict", "-Fallow-raw-deref=none",
                                "-Fstd-extern-specs=on", "-Zunstable-options"]
                    for kind in ("rmeta", "rlib"):
                        command += ["--extern", "force:fd_read_file_primitive=" + primitive["artifacts"][kind]]
                    command += ["-L", "dependency=" + str(Path(primitive["artifacts"]["rmeta"]).parent)]
                command.append(str(path))
                result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True, timeout=120)
                log = result.stdout + result.stderr
                log_name = f"{name}-{tool}.log"
                (output / log_name).write_text(log)
                report["runs"].append({"case": name, "tool": tool, "command": command,
                                       "exit_code": result.returncode, "log": log_name})
                print(f"{name}/{tool}: exit {result.returncode}", flush=True)
                if tool == "flux":
                    for line in log.splitlines():
                        if line.lstrip().startswith(("error", "summary.")):
                            print(line, flush=True)
                if tool == "rustc" and result.returncode:
                    raise RuntimeError("Ordinary compilation failed")
                if tool == "flux":
                    if any(word in log.lower() for word in ("internal compiler error", "internal flux error", "panicked at")):
                        report["status"] = "flux-crash"
                        raise RuntimeError("Flux crashed; review the diagnostic before changing the trust boundary")
                    if "unsupported" in log.lower():
                        report["status"] = "unsupported-checker-feature"
                        raise RuntimeError("Unsupported checker feature; no proof or mutation rejection established")
                    if name == "positive" and (result.returncode or "2 checked; 0 trusted; 0 ignored" not in log):
                        raise RuntimeError("Both sequential bodies must check; inspect positive-flux.log")
                    if name == "extra-byte" and (result.returncode == 0 or not DIAGNOSTIC.search(log)):
                        raise RuntimeError("Expected a proof rejection of the extra-byte mutation")
        report["status"] = "sequential-length-contract-checked-and-mutant-rejected"
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as error:
        report["failure"] = str(error)
        raise
    finally:
        (output / "result.json").write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
