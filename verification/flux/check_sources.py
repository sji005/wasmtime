#!/usr/bin/env python3
"""Check frozen fd_read dependencies and prohibit production changes at M0.

Hashes use UTF-8 source with CRLF normalized to LF, matching Git blob contents.
This is a provenance/change guard, not a call-graph completeness proof.
"""

import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT)


def digest(data):
    return hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest()


def main():
    manifest = json.loads((HERE / "sources.json").read_text())
    baseline = manifest["baseline"]
    assert baseline == json.loads((HERE / "pins.json").read_text())["baseline"], "baseline pin drift"
    subprocess.run(["git", "merge-base", "--is-ancestor", baseline, "HEAD"], cwd=ROOT, check=True)
    for path, expected in manifest["files"].items():
        assert digest(git("show", f"{baseline}:{path}")) == expected, f"baseline hash mismatch: {path}"
        assert digest((ROOT / path).read_bytes()) == expected, f"frozen dependency changed: {path}"
    paths = set(git("diff", "--name-only", baseline, "--").decode().splitlines())
    paths.update(git("ls-files", "--others", "--exclude-standard").decode().splitlines())
    for path in paths:
        assert (path.startswith("verification/flux/") or path in (
            ".github/workflows/flux-fd-read.yml", "crates/wiggle/tests/fd_read_memory.rs"
        )), f"M0 permits no production changes: {path}"
    coverage = json.loads((HERE / "coverage.json").read_text())
    ids = set()
    for row in coverage["edges"]:
        for field in ("id", "edge", "configuration", "source", "effect", "origin", "offset_count", "original_check", "sink", "status", "trust"):
            assert field in row, f"missing {field}: {row}"
        assert row["id"] not in ids, f"duplicate edge: {row['id']}"
        ids.add(row["id"])
        assert row["source"] in manifest["files"], f"unfrozen edge source: {row['source']}"
        assert row["status"] in ("open", "excluded", "trusted-boundary"), "M0 has no checked production bodies"
    print(f"PASS: {len(manifest['files'])} frozen inputs; {len(ids)} recorded fd_read edges; production unchanged")


if __name__ == "__main__":
    main()
