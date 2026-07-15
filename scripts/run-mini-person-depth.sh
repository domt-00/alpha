#!/usr/bin/env bash
# Compare person description depth: short (1-step) vs medium (2-step) vs full (4-step, existing).
# Uses ELECTRONICS-MINI scenario with basic item descriptions and Mistral.
#
# Usage (from DT Study directory):
#   nohup bash scripts/run-mini-person-depth.sh > logs/mini-person-depth.log 2>&1 &

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

log "=== Generating benchmarks with different person description depths ==="

log "Generating electronics-mini-person-short (1-step people)"
"$PYTHON" scripts/make-benchmark.py \
    --env-file "$ENV_PATH" \
    --scenarios ELECTRONICS-MINI \
    --benchmark electronics-mini-person-short \
    --num_setups 3 --num_people 3 \
    --seed_steps 1
log "electronics-mini-person-short done."

log "Generating electronics-mini-person-medium (2-step people)"
"$PYTHON" scripts/make-benchmark.py \
    --env-file "$ENV_PATH" \
    --scenarios ELECTRONICS-MINI \
    --benchmark electronics-mini-person-medium \
    --num_setups 3 --num_people 3 \
    --seed_steps 2
log "electronics-mini-person-medium done."

log "=== Running proxies ==="

for BENCH in electronics-mini-person-short electronics-mini-person-medium; do
    log "=== Proxies for $BENCH ==="

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

log "Generating plots"
mkdir -p data/experiments/plots
for BENCH in electronics-mini-person-short electronics-mini-person-medium; do
    "$PYTHON" scripts/vis-benchmark-fig.py "$BENCH" \
        --outprefix "data/experiments/plots/${BENCH}" || log "WARNING: vis failed for $BENCH"
done

log "ALL DONE."
