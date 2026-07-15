#!/usr/bin/env bash
# Qwen 2.5 7B (via Ollama) — VD2, NVD, H on electronics-mini-qwen.
# XOR and VD1 results come from the gemma-small run (same FullPerson data).
#
# Usage (from DT Study directory):
#   nohup bash scripts/run-qwen-experiment.sh > logs/qwen-experiment.log 2>&1 &
#   tail -f logs/qwen-experiment.log

cd "$(dirname "$0")/.."
mkdir -p logs

PYTHON="$(pwd)/venv/bin/python"
ENV=".env.qwen"
BENCH="electronics-mini-qwen"
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

CAP=20
MIN_ITER=3
MAX_ICA=30
CHECK="high"
TARGET="highest"
HAPPY="low"
EMPHASIS="Quickly explore the person's valuation and get to the essence of things"
ANCHOR="20 to 30"
NUM_Q=5
PAUSE=10

START_TIME=$(date '+%Y-%m-%d %H:%M:%S')
log "=== Qwen 2.5 7B experiment ==="
log "    Benchmark : $BENCH (3 items, 9 people, 3 setups)"
log "    Model     : qwen2.5:7b via Ollama"
log "    Proxies   : VD2, NVD, H"
log "    Start     : $START_TIME"

run() {
    local LABEL="$1"; local SCRIPT="$2"; shift 2
    log "--- $LABEL ---"
    "$PYTHON" "$SCRIPT" --benchmark "$BENCH" --env_path "$ENV" "$@" \
        || log "WARNING: $LABEL failed"
    sleep $PAUSE
}

run "Proxy-XOR" scripts/run-proxy-xor.py

run "Proxy-VD1" scripts/run-proxy-vd1.py \
    --cap $CAP --min_iterations $MIN_ITER --max_iterations $MAX_ICA \
    --check_priority "$CHECK" --target_bundle_priority "$TARGET" \
    --happy_priority "$HAPPY" --target_bundle_emphasis "$EMPHASIS" \
    --anchor_num_target_bundles "$ANCHOR"

run "Proxy-VD2" scripts/run-proxy-vd2.py \
    --cap $CAP --min_iterations $MIN_ITER --max_iterations $MAX_ICA \
    --check_priority "$CHECK" --target_bundle_priority "$TARGET" \
    --happy_priority "$HAPPY" --target_bundle_emphasis "$EMPHASIS" \
    --anchor_num_target_bundles "$ANCHOR"

run "Proxy-NVD" scripts/run-proxy-nvd.py \
    --num_questions $NUM_Q \
    --cap $CAP --min_iterations $MIN_ITER --max_iterations $MAX_ICA \
    --check_priority "$CHECK" --target_bundle_priority "$TARGET" \
    --happy_priority "$HAPPY" --target_bundle_emphasis "$EMPHASIS" \
    --anchor_num_target_bundles "$ANCHOR"

run "Proxy-H" scripts/run-proxy-h.py \
    --cap $CAP --min_iterations $MIN_ITER --max_iterations $MAX_ICA \
    --check_priority "$CHECK" --target_bundle_priority "$TARGET" \
    --happy_priority "$HAPPY" --target_bundle_emphasis "$EMPHASIS" \
    --anchor_num_target_bundles "$ANCHOR"

log "--- Results ---"
ls -lh "data/${BENCH}-logs/"*.csv 2>/dev/null || log "No result files found."
log "ALL DONE."
