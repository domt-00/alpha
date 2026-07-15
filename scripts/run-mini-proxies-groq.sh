#!/usr/bin/env bash
# Run all 5 proxies on the 3 mini benchmarks using Groq (Llama 3.3 70B).
# Usage (from DT Study directory):
#   nohup bash scripts/run-mini-proxies-groq.sh > logs/mini-pipeline-groq.log 2>&1 &

cd "$(dirname "$0")/.."
mkdir -p logs

PYTHON="$(pwd)/venv/bin/python"
ENV_PATH=".env.llama"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

CAP=20
MIN_ITER=0
CHECK="high"
TARGET="highest"
HAPPY="low"
EMPHASIS="Quickly explore the person's valuation and get to the essence of things"
ANCHOR="20 to 30"
NUM_Q=5

log "Starting 3-item mini proxy runs (Groq / Llama 3.3 70B)"

for BENCH in electronics-mini-groq electronics-mini-specs-groq electronics-mini-pdf-groq; do
    log "=== Running proxies for $BENCH ==="

    log "  Proxy-XOR: $BENCH"
    "$PYTHON" scripts/run-proxy-xor.py --benchmark "$BENCH" --env_path "$ENV_PATH" || log "WARNING: XOR failed for $BENCH"

    log "  Proxy-VD1: $BENCH"
    "$PYTHON" scripts/run-proxy-vd1.py --benchmark "$BENCH" --env_path "$ENV_PATH" \
        --cap $CAP --min_iterations $MIN_ITER \
        --check_priority "$CHECK" --target_bundle_priority "$TARGET" \
        --happy_priority "$HAPPY" --target_bundle_emphasis "$EMPHASIS" \
        --anchor_num_target_bundles "$ANCHOR" || log "WARNING: VD1 failed for $BENCH"

    log "  Proxy-VD2: $BENCH"
    "$PYTHON" scripts/run-proxy-vd2.py --benchmark "$BENCH" --env_path "$ENV_PATH" \
        --cap $CAP --min_iterations $MIN_ITER \
        --check_priority "$CHECK" --target_bundle_priority "$TARGET" \
        --happy_priority "$HAPPY" --target_bundle_emphasis "$EMPHASIS" \
        --anchor_num_target_bundles "$ANCHOR" || log "WARNING: VD2 failed for $BENCH"

    log "  Proxy-NVD: $BENCH"
    "$PYTHON" scripts/run-proxy-nvd.py --benchmark "$BENCH" --env_path "$ENV_PATH" \
        --num_questions $NUM_Q \
        --cap $CAP --min_iterations $MIN_ITER \
        --check_priority "$CHECK" --target_bundle_priority "$TARGET" \
        --happy_priority "$HAPPY" --target_bundle_emphasis "$EMPHASIS" \
        --anchor_num_target_bundles "$ANCHOR" || log "WARNING: NVD failed for $BENCH"

    log "  Proxy-H: $BENCH"
    "$PYTHON" scripts/run-proxy-h.py --benchmark "$BENCH" --env_path "$ENV_PATH" \
        --cap $CAP --min_iterations $MIN_ITER \
        --check_priority "$CHECK" --target_bundle_priority "$TARGET" \
        --happy_priority "$HAPPY" --target_bundle_emphasis "$EMPHASIS" \
        --anchor_num_target_bundles "$ANCHOR" || log "WARNING: H failed for $BENCH"

    log "$BENCH complete."
done

log "ALL DONE."
