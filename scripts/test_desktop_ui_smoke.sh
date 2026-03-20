#!/bin/bash

set -euo pipefail

cd "$(dirname "$0")/.." || exit 1
source scripts/uv_pytest.sh

OUT_DIR="${1:-/tmp/bao-desktop-ui-smoke}"
mkdir -p "$OUT_DIR"

trap 'status=$?; if [ "$status" -ne 0 ]; then echo "desktop ui smoke failed: inspect $OUT_DIR"; fi' EXIT

export BAO_DESKTOP_UI_SMOKE_DIR="$OUT_DIR"
run_uv_pytest desktop -q -m desktop_ui_smoke

echo "desktop ui smoke ok: $OUT_DIR"
