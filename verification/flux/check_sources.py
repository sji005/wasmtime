#!/usr/bin/env python3
"""Check frozen fd_read dependencies and permit only registered specifications.

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


def specification_only(annotation):
    text = annotation.strip()
    prefix = "#[cfg_attr(flux, flux::"
    if not text.startswith(prefix) or any(token in text for token in ('"', '//', '/*')):
        return False
    kind = text[len(prefix):].split("(", 1)[0]
    if kind not in ("sig", "refined_by", "field", "variant"):
        return False
    stack = []
    pairs = {')': '(', ']': '[', '}': '{'}
    for index, char in enumerate(text[1:], 1):
        if char in "([{":
            stack.append(char)
        elif char in ")]}":
            if not stack or stack.pop() != pairs[char]:
                return False
            if not stack and index != len(text) - 1:
                return False
    return not stack


def main():
    manifest = json.loads((HERE / "sources.json").read_text())
    baseline = manifest["baseline"]
    annotations = json.loads((HERE / "annotations.json").read_text())
    assert set(annotations) <= set(manifest["files"]), "annotation outside frozen dependencies"
    assert baseline == json.loads((HERE / "pins.json").read_text())["baseline"], "baseline pin drift"
    subprocess.run(["git", "merge-base", "--is-ancestor", baseline, "HEAD"], cwd=ROOT, check=True)
    for path, expected in manifest["files"].items():
        original = git("show", f"{baseline}:{path}").decode().replace("\r\n", "\n")
        assert digest(original.encode()) == expected, f"baseline hash mismatch: {path}"
        annotated = original
        for addition in annotations.get(path, []):
            anchor, annotation = addition["anchor"], addition["annotation"]
            assert specification_only(annotation), "only a single whitelisted Flux specification attribute is allowed"
            expected_count = addition.get("expected_count", 1)
            occurrence = addition.get("occurrence", 0)
            assert annotated.count(anchor) == expected_count, f"ambiguous specification site: {path}"
            assert 0 <= occurrence < expected_count, "invalid specification occurrence"
            at = -1
            for _ in range(occurrence + 1):
                at = annotated.index(anchor, at + 1)
            annotated = annotated[:at] + annotation + annotated[at:]
        assert (ROOT / path).read_text(encoding="utf-8") == annotated, f"non-specification production change: {path}"
    paths = set(git("diff", "--name-only", baseline, "--").decode().splitlines())
    paths.update(git("ls-files", "--others", "--exclude-standard").decode().splitlines())
    for path in paths:
        assert (path.startswith("verification/flux/") or path in annotations or path in (
            ".github/workflows/flux-fd-read.yml",
            "crates/wiggle/tests/fd_read_memory.rs",
            "crates/wasi/tests/fd_read_memory.rs",
        )), f"unregistered production change: {path}"
    coverage = json.loads((HERE / "coverage.json").read_text())
    ids = set()
    for row in coverage["edges"]:
        for field in ("id", "edge", "configuration", "source", "effect", "origin", "offset_count", "original_check", "sink", "status", "trust"):
            assert field in row, f"missing {field}: {row}"
        assert row["id"] not in ids, f"duplicate edge: {row['id']}"
        ids.add(row["id"])
        assert row["source"] in manifest["files"], f"unfrozen edge source: {row['source']}"
        assert row["status"] in ("open", "excluded", "trusted-boundary"), "M0 has no checked production bodies"
    print(f"PASS: {len(manifest['files'])} frozen inputs; {len(ids)} recorded fd_read edges; production differs only by {sum(map(len, annotations.values()))} registered Flux specification attribute(s)")


if __name__ == "__main__":
    main()
