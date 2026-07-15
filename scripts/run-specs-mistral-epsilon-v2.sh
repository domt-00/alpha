#!/usr/bin/env bash
# Mistral — VD2 epsilon (discount) sensitivity, v2.
#
# Fixes vs run-specs-mistral-epsilon.sh:
#   1. MAX_ICA=30 (was 10) — now matches run-deepseek-epsilon.sh exactly, so
#      auctions get the same room to reach competitive equilibrium instead of
#      being cut off early (2 of 9 prior runs hit the old MAX_ICA=10 ceiling).
#   2. Adds discount=0.70 and 0.80 (+-0.05 around 0.75) alongside the original
#      0.5/0.75/1.0, to see whether small discount changes move efficiency as
#      much as large ones.
#   3. Whole run wrapped in `caffeinate` — the previous discount=0.75 run took
#      19h instead of ~50min because the laptop slept for most of it (222
#      sleep/wake cycles logged during that window vs 0 during the fast runs).
#      caffeinate -dis keeps the system, display, and disk awake for this
#      script's PID so that doesn't happen again.
#
# Usage (from DT Study directory):
#   nohup bash scripts/run-specs-mistral-epsilon-v2.sh > logs/specs-mistral-epsilon-v2.log 2>&1 &
#   tail -f logs/specs-mistral-epsilon-v2.log

cd "$(dirname "$0")/.."
mkdir -p logs

PYTHON="$(pwd)/venv/bin/python"
ENV=".env.mistral"
BENCH="electronics-specs-mistral-v2"
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

CAP=20
MIN_ITER=3
MAX_ICA=30
CHECK="high"
TARGET="highest"
HAPPY="low"
EMPHASIS="Quickly explore the person's valuation and get to the essence of things"
ANCHOR="20 to 30"
PAUSE=15

log "=== Mistral (mistral-small-latest) — VD2 epsilon sensitivity v2 ==="
log "    Benchmark : $BENCH"
log "    Discounts : 0.5, 0.70, 0.75, 0.80, 1.0"
log "    max_iterations = $MAX_ICA (matches DeepSeek epsilon script)"
log "    min_iterations = $MIN_ITER"
log "    caffeinate active — system will not sleep for this run"

for DISCOUNT in 0.5 0.70 0.75 0.80 1.0; do
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
