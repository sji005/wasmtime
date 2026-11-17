#!/usr/bin/env python3
"""Capture and inspect the actual nightly-expanded P1 fd_read ABI wrapper.

Syntactic evidence only: this is not a proof of the generated function.
"""

import argparse
import hashlib
import json
from pathlib import Path
import re


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("expanded", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    text = args.expanded.read_text(encoding="utf-8")
    candidates = list(re.finditer(r"(?m)^([ \t]*)pub async fn fd_read\s*\(", text))
    # Enabling p1 also compiles the legacy P0 compatibility module. Select the
    # P1 trait explicitly rather than assuming every fd_read belongs to P1.
    matches = [m for m in candidates if "WasiSnapshotPreview1" in text[m.start():text.index("{", m.end())]]
    if len(matches) != 1:
        raise SystemExit(f"Expected one public async fd_read ABI wrapper; found {len(matches)}")
    match = matches[0]
    body = text.index("{", match.end())
    end = re.search(r"(?m)^" + re.escape(match[1]) + r"}\s*$", text[body:])
    if end is None:
        raise SystemExit("Could not locate formatted fd_read wrapper closing brace")
    snippet = text[match.start():body + end.end()] + "\n"
    compact = re.sub(r"\s+", "", snippet)
    for number in range(4):
        if f"arg{number}:i32" not in compact:
            raise SystemExit(f"Missing expected ABI parameter arg{number}: i32")
    call = re.search(r"WasiSnapshotPreview1::fd_read\(ctx,memory,", compact)
    store = re.search(r"memory\.write\(wiggle::GuestPtr::<Size>::new\(arg3asu32\),", compact)
    if call is None or store is None or store.start() < call.start():
        print("\n".join(line for line in snippet.splitlines() if any(s in line for s in ("fd_read", "GuestPtr", "arg3", "memory.write"))))
        raise SystemExit("Expected trait fd_read call followed by arg3 Size result store")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "fd-read-glue.rs").write_text(snippet, encoding="utf-8", newline="\n")
    evidence = {
        "claim": "Expanded ABI syntax inspected; function and memory effects remain unproved",
        "target": "x86_64-unknown-linux-gnu",
        "features": ["p1", "p2"],
        "selection": "WasiSnapshotPreview1 trait; legacy P0 wrapper excluded",
        "public_fd_read_wrappers_seen": len(candidates),
        "rustc_commit": "1a2c4797ef2570bd76ca5dee34449169bc7dc457",
        "expanded_source_line": text[:match.start()].count("\n") + 1,
        "wrapper_sha256": hashlib.sha256(snippet.encode()).hexdigest(),
        "abi_arguments": {"arg0": "fd", "arg1": "iovs pointer", "arg2": "iovs count", "arg3": "nread output pointer"},
        "observed_output": "Size store through arg3 after the fd_read trait call; Size is u32 in typenames.witx",
        "remaining": ["Flux proof of expanded wrapper", "exact control-flow/error framing", "pointer validity, alignment and aliases", "actual allocation binding"],
    }
    (args.output_dir / "evidence.json").write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(evidence, indent=2))
    print("PASS: actual expanded fd_read ABI and nread store captured")


if __name__ == "__main__":
    main()
