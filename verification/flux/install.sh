#!/usr/bin/env bash
# Linux x86-64 only. Run on Ubuntu 24.04 or newer (Z3 requires glibc 2.39).
set -euo pipefail

FLUX_REV=b68c177c5ace7cb3644fdeea140dc5d18669c6cc
Z3_SHA=d56f60b06f432f33de5810f7f1a384a339131f361e2d54d08ea83eea14326880
FIXPOINT_SHA=7f23b085b848d42ce91618c722cf867ca16e2b570d5d2427138ed80a99d80f9a

if [[ "$(uname -s)-$(uname -m)" != Linux-x86_64 ]]; then
    echo 'This verification toolchain requires x86-64 Linux.' >&2
    exit 1
fi
command -v rustup >/dev/null
bin="${CARGO_HOME:-$HOME/.cargo}/bin"
mkdir -p "$bin"
export PATH="$bin:$PATH"
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

curl --fail --location --retry 3 \
    https://github.com/Z3Prover/z3/releases/download/z3-5.3.3/z3-5.3.3-x64-glibc-2.39.zip \
    --output "$work/z3.zip"
echo "$Z3_SHA  $work/z3.zip" | sha256sum --check
unzip -q "$work/z3.zip" -d "$work/z3"
install -m755 "$work/z3/z3-5.3.3-x64-glibc-2.39/bin/z3" "$bin/z3"

# The nightly URL can change. The digest is authoritative: changed content
# must fail rather than silently changing the prover used by this experiment.
curl --fail --location --retry 3 \
    https://github.com/ucsd-progsys/liquid-fixpoint/releases/download/nightly/fixpoint-x86_64-linux-gnu.tar.gz \
    --output "$work/fixpoint.tar.gz"
echo "$FIXPOINT_SHA  $work/fixpoint.tar.gz" | sha256sum --check
tar -xzf "$work/fixpoint.tar.gz" -C "$bin"
chmod +x "$bin/fixpoint"

git init -q "$work/flux"
git -C "$work/flux" remote add origin https://github.com/flux-rs/flux.git
git -C "$work/flux" fetch --depth 1 origin "$FLUX_REV"
git -C "$work/flux" checkout --detach FETCH_HEAD
test "$(git -C "$work/flux" rev-parse HEAD)" = "$FLUX_REV"
# Pin the external contracts reviewed for the M0 probes as well as the checker.
python3 - "$work/flux" <<'PY'
import json
from pathlib import Path
import subprocess
import sys
pins = json.loads(Path('verification/flux/pins.json').read_text())
for path, expected in pins['reviewed_flux_spec_git_blobs'].items():
    actual = subprocess.check_output(['git', '-C', sys.argv[1], 'hash-object', path], text=True).strip()
    if actual != expected:
        raise SystemExit(f'Flux primitive specification changed: {path}')
PY
(
    cd "$work/flux"
    cargo xtask install
)
flux --version
z3 --version
fixpoint --version
