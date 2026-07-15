#!/usr/bin/env bash
# Discount sensitivity analysis using Cerebras (gpt-oss-120b).
# Runs VD1 and VD2 on electronics-mini at discounts 0.5, 0.75, 1.0.
# All three on same provider for a clean self-consistent comparison.
# Results go to data/electronics-mini-logs/ with Proxy-discount column.
#
# Usage (from DT Study directory):
#   nohup bash scripts/run-discount-sensitivity-cerebras.sh > logs/discount-sensitivity-cerebras.log 2>&1 &

cd "$(dirname "$0")/.."
mkdir -p logs

PYTHON="$(pwd)/venv/bin/python"
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

BENCH="electronics-mini"
ENV=".env.cerebras"
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
    log "  Waiting 30s..."
    sleep 30
}

log "=== Discount sensitivity (Cerebras) — VD1 + VD2 on $BENCH ==="
log "    Provider: gpt-oss-120b via Cerebras"
log "    Discounts: 0.5, 0.75, 1.0"

for DISCOUNT in 0.5 0.75 1.0; do
    log "--- discount = $DISCOUNT ---"
    run_proxy "VD1" scripts/run-proxy-vd1.py $DISCOUNT
    run_proxy "VD2" scripts/run-proxy-vd2.py $DISCOUNT
done

log "ALL DONE. Results in data/electronics-mini-logs/ — filter by Proxy-discount column."
