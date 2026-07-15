#!/usr/bin/env bash
# 3-item mini pipeline: IPAD9 + IPAD12 + APPLEPENCILPRO
# Runs all 3 description variants (basic, specs, pdf) × 5 proxies using Mistral.
#
# Usage (from DT Study directory):
#   nohup bash scripts/run-mini-pipeline.sh > logs/mini-pipeline.log 2>&1 &
#   tail -f logs/mini-pipeline.log

set -e
cd "$(dirname "$0")/.."
mkdir -p logs

PYTHON="$(pwd)/venv/bin/python"
ENV_PATH=".env"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

CAP=20
MIN_ITER=0
CHECK="high"
TARGET="highest"
HAPPY="low"
EMPHASIS="Quickly explore the person's valuation and get to the essence of things"
ANCHOR="20 to 30"
NUM_Q=5

log "Starting 3-item mini pipeline (Mistral)"

# Step 1: Generate benchmarks for all 3 mini variants
for SCENARIO in ELECTRONICS-MINI ELECTRONICS-MINI-SPECS ELECTRONICS-MINI-PDF; do
    BENCH=$(echo "$SCENARIO" | tr '[:upper:]' '[:lower:]')
    log "Generating benchmark: $BENCH"
    "$PYTHON" scripts/make-benchmark.py \
        --env-file "$ENV_PATH" \
        --scenarios "$SCENARIO" \
        --benchmark "$BENCH" \
        --num_setups 3 \
        --num_people 3
    log "Benchmark $BENCH done."
done

# Step 2: Run all 5 proxies on each benchmark
for BENCH in electronics-mini electronics-mini-specs electronics-mini-pdf; do
    log "=== Running proxies for $BENCH ==="

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

# Step 3: Generate plots
log "Generating visualisations"
mkdir -p data/experiments/plots
for BENCH in electronics-mini electronics-mini-specs electronics-mini-pdf; do
    "$PYTHON" scripts/vis-benchmark-fig.py "$BENCH" \
        --outprefix "data/experiments/plots/${BENCH}" || \
        log "WARNING: vis failed for $BENCH"
done

log "ALL DONE. Results in data/experiments/plots/"
