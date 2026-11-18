#!/usr/bin/env bash
# Build a separately selected driver; retain the baseline driver/spec sysroot.
set -euo pipefail
repo_root=$(pwd)
evidence="$repo_root/artifacts/fd-read/compat-toolchain"
driver_dir="${RUNNER_TEMP:?}/fd-read-compat-driver"
mkdir -p "$evidence" "$driver_dir"
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
rev=b68c177c5ace7cb3644fdeea140dc5d18669c6cc
git init -q "$work/flux"
git -C "$work/flux" remote add origin https://github.com/flux-rs/flux.git
git -C "$work/flux" fetch --depth 1 origin "$rev"
git -C "$work/flux" checkout --detach FETCH_HEAD
test "$(git -C "$work/flux" rev-parse HEAD)" = "$rev"
patch="$repo_root/verification/flux/toolchain/include-selection.patch"
git -C "$work/flux" apply --check "$patch"
git -C "$work/flux" apply "$patch"
git -C "$work/flux" diff --check
git -C "$work/flux" diff > "$evidence/applied.patch"
(
    cd "$work/flux"
    cargo +nightly-2026-10-22 build --locked --release -p flux-driver
) 2>&1 | tee "$evidence/build.log"
install -m755 "$work/flux/target/release/flux-driver" "$driver_dir/flux-driver"
python3 - "$driver_dir/flux-driver" "$patch" "$evidence/receipt.json" <<'PY'
import hashlib, json, subprocess, sys
from pathlib import Path
driver, patch, output = map(Path, sys.argv[1:])
receipt = {
    'base_revision': 'b68c177c5ace7cb3644fdeea140dc5d18669c6cc',
    'patch': 'verification/flux/toolchain/include-selection.patch',
    'patch_sha256': hashlib.sha256(patch.read_bytes()).hexdigest(),
    'driver_sha256': hashlib.sha256(driver.read_bytes()).hexdigest(),
    'rustc': subprocess.check_output(['rustc', '+nightly-2026-10-22', '-vV'], text=True),
    'scope': 'Function selection/path matching only; no inference, arithmetic, solver or primitive-spec changes',
    'standard_specs': 'Unmodified baseline Flux sysroot; see pins.json',
    'status': 'candidate; require selection regressions and strict M0 positive/negative gate'
}
output.write_text(json.dumps(receipt, indent=2)+'\n')
PY
echo "FLUX_DRIVER=$driver_dir/flux-driver" >> "$GITHUB_ENV"
echo "FLUX_COMPAT_RECEIPT=$evidence/receipt.json" >> "$GITHUB_ENV"
