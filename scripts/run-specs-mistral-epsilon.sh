#!/usr/bin/env bash
# Mistral — VD2 epsilon (discount) sensitivity: 0.5, 0.75, 1.0
# Same design as run-deepseek-epsilon.sh, on electronics-specs-mistral-v2.
# min_iterations=3 (fixed value, not the buggy 0 used in the first Mistral pass).
#
# Usage (from DT Study directory):
#   nohup bash scripts/run-specs-mistral-epsilon.sh > logs/specs-mistral-epsilon.log 2>&1 &
#   tail -f logs/specs-mistral-epsilon.log

cd "$(dirname "$0")/.."
mkdir -p logs

PYTHON="$(pwd)/venv/bin/python"
ENV=".env.mistral"
BENCH="electronics-specs-mistral-v2"
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

CAP=20
MIN_ITER=3
MAX_ICA=10
CHECK="high"
TARGET="highest"
HAPPY="low"
EMPHASIS="Quickly explore the person's valuation and get to the essence of things"
ANCHOR="20 to 30"
PAUSE=15

log "=== Mistral (mistral-small-latest) — VD2 epsilon sensitivity ==="
log "    Benchmark : $BENCH"
log "    Discounts : 0.5, 0.75, 1.0"
log "    min_iterations = $MIN_ITER"

for DISCOUNT in 0.5 0.75 1.0; do
    T0=$(date +%s)
    log "--- VD2 discount=${DISCOUNT} ---"
    "$PYTHON" scripts/run-proxy-vd2.py \
        --benchmark "$BENCH" --env_path "$ENV" \
        --cap $CAP --min_iterations $MIN_ITER --max_iterations $MAX_ICA \
        --check_priority "$CHECK" --target_bundle_priority "$TARGET" \
        --happy_priority "$HAPPY" --target_bundle_emphasis "$EMPHASIS" \
        --anchor_num_target_bundles "$ANCHOR" \
        --discount $DISCOUNT \
        || log "WARNING: VD2 discount=${DISCOUNT} failed"
    log "discount=${DISCOUNT} done in $(( $(date +%s) - T0 ))s."
    sleep $PAUSE
done

log "--- Results ---"
ls -lh "data/${BENCH}-logs/"*VD2*.csv 2>/dev/null || log "No VD2 result files found."

log "ALL DONE. Run: python scripts/build-run-registry.py --print"
