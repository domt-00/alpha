#!/usr/bin/env bash
# Full pipeline using Cerebras gpt-oss-120b API.
#
# Usage (from DT Study directory):
#   nohup bash scripts/run-cerebras-pipeline.sh > logs/cerebras-pipeline.log 2>&1 &
#   tail -f logs/cerebras-pipeline.log

set -e
cd "$(dirname "$0")/.."
mkdir -p logs

PYTHON="$(pwd)/venv/bin/python"
ENV_PATH=".env.cerebras"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

CAP=20
MIN_ITER=0
CHECK="high"
TARGET="highest"
HAPPY="low"
EMPHASIS="Quickly explore the person's valuation and get to the essence of things"
ANCHOR="20 to 30"
NUM_Q=5

log "Starting Cerebras gpt-oss-120b pipeline"
log "Using env: $ENV_PATH"

for BENCH in electronics-cerebras electronics-specs-cerebras electronics-reviews-cerebras; do
    log "Running proxies for $BENCH"

    log "  Proxy-XOR: $BENCH"
    "$PYTHON" scripts/run-proxy-xor.py --benchmark "$BENCH" --env_path "$ENV_PATH"

    log "  Proxy-VD1: $BENCH"
    "$PYTHON" scripts/run-proxy-vd1.py --benchmark "$BENCH" --env_path "$ENV_PATH" \
        --cap $CAP --min_iterations $MIN_ITER \
        --check_priority "$CHECK" --target_bundle_priority "$TARGET" \
        --happy_priority "$HAPPY" --target_bundle_emphasis "$EMPHASIS" \
        --anchor_num_target_bundles "$ANCHOR"

    log "  Proxy-VD2: $BENCH"
    "$PYTHON" scripts/run-proxy-vd2.py --benchmark "$BENCH" --env_path "$ENV_PATH" \
        --cap $CAP --min_iterations $MIN_ITER \
        --check_priority "$CHECK" --target_bundle_priority "$TARGET" \
        --happy_priority "$HAPPY" --target_bundle_emphasis "$EMPHASIS" \
        --anchor_num_target_bundles "$ANCHOR"

    log "  Proxy-NVD: $BENCH"
    "$PYTHON" scripts/run-proxy-nvd.py --benchmark "$BENCH" --env_path "$ENV_PATH" \
        --num_questions $NUM_Q \
        --cap $CAP --min_iterations $MIN_ITER \
        --check_priority "$CHECK" --target_bundle_priority "$TARGET" \
        --happy_priority "$HAPPY" --target_bundle_emphasis "$EMPHASIS" \
        --anchor_num_target_bundles "$ANCHOR"

    log "  Proxy-H: $BENCH"
    "$PYTHON" scripts/run-proxy-h.py --benchmark "$BENCH" --env_path "$ENV_PATH" \
        --cap $CAP --min_iterations $MIN_ITER \
        --check_priority "$CHECK" --target_bundle_priority "$TARGET" \
        --happy_priority "$HAPPY" --target_bundle_emphasis "$EMPHASIS" \
        --anchor_num_target_bundles "$ANCHOR"

    log "$BENCH complete."
done

log "Generating visualisations"
mkdir -p data/experiments/plots
for BENCH in electronics-cerebras electronics-specs-cerebras electronics-reviews-cerebras; do
    "$PYTHON" scripts/vis-benchmark-fig.py "$BENCH" \
        --outprefix "data/experiments/plots/${BENCH}" || \
        log "WARNING: vis failed for $BENCH"
done

log "ALL DONE. Cerebras results in data/experiments/plots/"
