#!/usr/bin/env bash
# Mistral — H re-run on electronics-specs-mistral-v2 after fixing the
# CAP_INTERACTIONS bug in ceca_llmxor.py (real check was commented out,
# replaced with a hardcoded >128 — see convergence chart discussion).
# max_iterations=30 (not 10) to give the auction room to actually converge
# and avoid a repeat of the earlier truncation issue.
#
# Usage (from DT Study directory):
#   nohup caffeinate -dis bash scripts/run-specs-mistral-h-refixed.sh > logs/specs-mistral-h-refixed.log 2>&1 &
#   tail -f logs/specs-mistral-h-refixed.log

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

log "=== Mistral — H re-run (CAP_INTERACTIONS fixed) on $BENCH ==="
log "    min_iterations=$MIN_ITER  max_iterations=$MAX_ICA  cap=$CAP"
log ""

T0=$(date +%s)
log "--- H ---"
"$PYTHON" scripts/run-proxy-h.py \
    --benchmark "$BENCH" --env_path "$ENV" \
    --cap $CAP --min_iterations $MIN_ITER --max_iterations $MAX_ICA \
    --check_priority "$CHECK" --target_bundle_priority "$TARGET" --happy_priority "$HAPPY" \
    --target_bundle_emphasis "$EMPHASIS" --anchor_num_target_bundles "$ANCHOR" \
    || log "ERROR: H failed"
log "H done in $(( $(date +%s) - T0 ))s."

log ""
log "=== ALL DONE ==="
log "Run: python scripts/build-run-registry.py --print"
