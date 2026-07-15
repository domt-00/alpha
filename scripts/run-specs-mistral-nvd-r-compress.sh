#!/usr/bin/env bash
# Run NVD-R (Restrict+Prune combined) with --compress_description on
# electronics-specs-mistral-v2 (Mistral, mistral-small-latest).
#
# min_iterations=3 (matches the fixed run — see run-specs-mistral-all-fixed.sh).
# Writes to the same data/electronics-specs-mistral-v2-logs/ folder as the
# other Mistral results, labeled log_Proxy-NVD-R_*.
#
# Usage (from DT Study directory):
#   nohup bash scripts/run-specs-mistral-nvd-r-compress.sh > logs/specs-mistral-nvd-r-compress.log 2>&1 &
#   tail -f logs/specs-mistral-nvd-r-compress.log

cd "$(dirname "$0")/.."
mkdir -p logs

PYTHON="$(pwd)/venv/bin/python"
ENV=".env.mistral"
BENCH="electronics-specs-mistral-v2"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

CAP=20
MIN_ITER=3
MAX_ICA=10
NUM_Q=5
CHECK="high"
TARGET="highest"
HAPPY="low"
EMPHASIS="Quickly explore the person's valuation and get to the essence of things"
ANCHOR="20 to 30"

log "=== Electronics Specs — Mistral — NVD-R (Restrict+Prune) with compress_description ==="
log "    Benchmark : $BENCH  (6 items, 3 setups)"
log "    min_iterations = $MIN_ITER"
log "    Logs      : data/${BENCH}-logs/"
log ""

T0=$(date +%s)
log "--- NVD-R (compress_description) ---"
"$PYTHON" scripts/run-proxy-nvd-r.py \
    --benchmark "$BENCH" --env_path "$ENV" \
    --num_questions $NUM_Q \
    --cap $CAP --min_iterations $MIN_ITER --max_iterations $MAX_ICA \
    --check_priority "$CHECK" \
    --target_bundle_priority "$TARGET" \
    --happy_priority "$HAPPY" \
    --target_bundle_emphasis "$EMPHASIS" \
    --anchor_num_target_bundles "$ANCHOR" \
    --compress_description \
    || { log "ERROR: NVD-R failed"; exit 1; }
T1=$(date +%s)
log "NVD-R done in $((T1-T0))s."

log ""
log "=== ALL DONE ==="
log "Run: python scripts/build-run-registry.py --print"
