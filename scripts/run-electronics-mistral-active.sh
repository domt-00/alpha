#!/usr/bin/env bash
# Mistral — NVD-Active only on electronics-mistral (original, non-specs benchmark).
# Split out from the combined Ensemble+Active script after Ensemble hit sustained
# rate-limiting (Ensemble's 3x call multiplier + existing thread/process
# concurrency pushed well past Mistral's 100 req/min account limit).
# Active has no such multiplier (same per-bundle call count as plain NVD),
# so should not hit the same wall.
#
# Usage (from DT Study directory):
#   nohup caffeinate -dis bash scripts/run-electronics-mistral-active.sh > logs/electronics-mistral-active.log 2>&1 &
#   tail -f logs/electronics-mistral-active.log

cd "$(dirname "$0")/.."
mkdir -p logs

PYTHON="$(pwd)/venv/bin/python"
ENV=".env.mistral"
BENCH="electronics-mistral"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

CAP=20
MIN_ITER=3
MAX_ICA=30
NUM_Q=5
CHECK="high"
TARGET="highest"
HAPPY="low"
EMPHASIS="Quickly explore the person's valuation and get to the essence of things"
ANCHOR="20 to 30"

log "=== Mistral — NVD-Active on electronics-mistral (original, non-specs) ==="
log "    min_iterations=$MIN_ITER  max_iterations=$MAX_ICA"
log ""

T0=$(date +%s)
log "--- NVD-Active ---"
"$PYTHON" scripts/run-proxy-nvd-active.py \
    --benchmark "$BENCH" --env_path "$ENV" \
    --num_questions $NUM_Q --cap $CAP --min_iterations $MIN_ITER --max_iterations $MAX_ICA \
    --check_priority "$CHECK" --target_bundle_priority "$TARGET" --happy_priority "$HAPPY" \
    --target_bundle_emphasis "$EMPHASIS" --anchor_num_target_bundles "$ANCHOR" \
    || log "ERROR: NVD-Active failed"
log "NVD-Active done in $(( $(date +%s) - T0 ))s."

log ""
log "=== ALL DONE ==="
log "Run: python scripts/build-run-registry.py --print"
