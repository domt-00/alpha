#!/usr/bin/env bash
# Discount sensitivity analysis for VD1 and VD2 on electronics-mini (Mistral).
# Tests discount values 0.5, 0.75, 1.0 — 0.75 is already run as baseline.
# Results go to electronics-mini-logs/ with Proxy-discount column for identification.
#
# Usage (from DT Study directory):
#   nohup bash scripts/run-discount-sensitivity.sh > logs/discount-sensitivity.log 2>&1 &

cd "$(dirname "$0")/.."
mkdir -p logs

PYTHON="$(pwd)/venv/bin/python"
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

BENCH="electronics-mini"
ENV=".env"
CAP=20; MIN_ITER=0; CHECK="high"; TARGET="highest"; HAPPY="low"
EMPHASIS="Quickly explore the person's valuation and get to the essence of things"
ANCHOR="20 to 30"

run_proxy() {
    local PROXY="$1"
    local SCRIPT="$2"
    local DISCOUNT="$3"
    log "  $PROXY discount=$DISCOUNT"
    "$PYTHON" "$SCRIPT" --benchmark "$BENCH" --env_path "$ENV" \
        --cap $CAP --min_iterations $MIN_ITER \
        --check_priority "$CHECK" --target_bundle_priority "$TARGET" \
        --happy_priority "$HAPPY" --target_bundle_emphasis "$EMPHASIS" \
        --anchor_num_target_bundles "$ANCHOR" \
        --discount "$DISCOUNT" || log "WARNING: $PROXY discount=$DISCOUNT failed"
    log "  Waiting 90s..."
    sleep 90
}

log "=== Discount sensitivity: VD1 and VD2 on $BENCH ==="

log "--- discount = 0.5 ---"
run_proxy "VD1" scripts/run-proxy-vd1.py 0.5
run_proxy "VD2" scripts/run-proxy-vd2.py 0.5

log "--- discount = 1.0 ---"
run_proxy "VD1" scripts/run-proxy-vd1.py 1.0
run_proxy "VD2" scripts/run-proxy-vd2.py 1.0

log "ALL DONE. Results in data/electronics-mini-logs/ — filter by Proxy-discount column."
