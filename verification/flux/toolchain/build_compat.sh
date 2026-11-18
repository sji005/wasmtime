#!/usr/bin/env bash
# Build a separately selected driver; retain the baseline driver/spec sysroot.
set -euo pipefail
repo_root=$(pwd)
evidence="$repo_root/artifacts/fd-read/compat-toolchain"
driver_dir="$HOME/.cache/fd-read-flux-compat"
mkdir -p "$evidence" "$driver_dir"
patches=(
    "$repo_root/verification/flux/toolchain/include-selection.patch"
    "$repo_root/verification/flux/toolchain/associated-field-normalization.patch"
    "$repo_root/verification/flux/toolchain/strict-type-projections.patch"
    "$repo_root/verification/flux/toolchain/opaque-diagnostic.patch"
    "$repo_root/verification/flux/toolchain/rpitit-signature-shape.patch"
)
if python3 - "$driver_dir" "${patches[@]}" <<'PY'
import hashlib, json, sys
from pathlib import Path
directory = Path(sys.argv[1])
try:
    receipt = json.loads((directory/'receipt.json').read_text())
    expected = {Path(p).name: hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in sys.argv[2:]}
    assert receipt['patches'] == expected
    assert receipt['driver_sha256'] == hashlib.sha256((directory/'flux-driver').read_bytes()).hexdigest()
except (OSError, KeyError, ValueError, AssertionError):
    sys.exit(1)
PY
then
    cp "$driver_dir/receipt.json" "$evidence/receipt.json"
    cat "${patches[@]}" > "$evidence/applied.patch"
    echo 'Restored matching driver and patch receipts.' > "$evidence/build.log"
    echo "FLUX_DRIVER=$driver_dir/flux-driver" >> "$GITHUB_ENV"
    echo "FLUX_COMPAT_RECEIPT=$evidence/receipt.json" >> "$GITHUB_ENV"
    exit 0
fi
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
rev=b68c177c5ace7cb3644fdeea140dc5d18669c6cc
git init -q "$work/flux"
git -C "$work/flux" remote add origin https://github.com/flux-rs/flux.git
git -C "$work/flux" fetch --depth 1 origin "$rev"
git -C "$work/flux" checkout --detach FETCH_HEAD
test "$(git -C "$work/flux" rev-parse HEAD)" = "$rev"
for patch in "${patches[@]}"; do
    git -C "$work/flux" apply --check "$patch"
    git -C "$work/flux" apply "$patch"
done
git -C "$work/flux" diff --check
git -C "$work/flux" diff > "$evidence/applied.patch"
(
    cd "$work/flux"
    cargo +nightly-2026-10-22 build --locked --release -p flux-driver
) 2>&1 | tee "$evidence/build.log"
install -m755 "$work/flux/target/release/flux-driver" "$driver_dir/flux-driver"
python3 - "$driver_dir/flux-driver" "$evidence/receipt.json" "${patches[@]}" <<'PY'
import hashlib, json, subprocess, sys
from pathlib import Path
driver, output = map(Path, sys.argv[1:3])
receipt = {
    'base_revision': 'b68c177c5ace7cb3644fdeea140dc5d18669c6cc',
    'patches': {Path(p).name: hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in sys.argv[3:]},
    'driver_sha256': hashlib.sha256(driver.read_bytes()).hexdigest(),
    'rustc': subprocess.check_output(['rustc', '+nightly-2026-10-22', '-vV'], text=True),
    'scope': 'Function selection, Rust ghost-shape normalization, fail-closed type projections, opaque diagnostics and RPITIT signature comparison; no solver, arithmetic or primitive-spec changes',
    'standard_specs': 'Unmodified baseline Flux sysroot; see pins.json',
    'status': 'candidate; require selection regressions and strict M0 positive/negative gate'
}
output.write_text(json.dumps(receipt, indent=2)+'\n')
PY
cp "$evidence/receipt.json" "$driver_dir/receipt.json"
echo "FLUX_DRIVER=$driver_dir/flux-driver" >> "$GITHUB_ENV"
echo "FLUX_COMPAT_RECEIPT=$evidence/receipt.json" >> "$GITHUB_ENV"
