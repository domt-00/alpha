#!/usr/bin/env bash
# Re-run the VD2 benchmarks that still showed 0% after the first fix attempt
# (rate limits hit the unretried thinking call; now fixed with @retry wrapper).
# Adds a 60s pause between benchmarks to avoid Mistral rate limits.
#
# Usage (from DT Study directory):
#   nohup bash scripts/rerun-vd2-fix2.sh > logs/rerun-vd2-fix2.log 2>&1 &

cd "$(dirname "$0")/.."
mkdir -p logs

PYTHON="$(pwd)/venv/bin/python"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

CAP=20
MIN_ITER=0
CHECK="high"
TARGET="highest"
HAPPY="low"
EMPHASIS="Quickly explore the person's valuation and get to the essence of things"
ANCHOR="20 to 30"

run_vd2() {
    local BENCH="$1"
    local ENV="$2"
    log "  Proxy-VD2: $BENCH (env=$ENV)"
    "$PYTHON" scripts/run-proxy-vd2.py --benchmark "$BENCH" --env_path "$ENV" \
        --cap $CAP --min_iterations $MIN_ITER \
        --check_priority "$CHECK" --target_bundle_priority "$TARGET" \
        --happy_priority "$HAPPY" --target_bundle_emphasis "$EMPHASIS" \
        --anchor_num_target_bundles "$ANCHOR" || log "WARNING: VD2 failed for $BENCH"
    log "  Waiting 90s for rate limit recovery..."
    sleep 90
}

log "=== Re-running failed VD2 benchmarks (with rate-limit recovery pauses) ==="

log "--- Mistral ---"
run_vd2 electronics-mini-specs         .env
run_vd2 electronics-mini-person-short  .env
run_vd2 electronics-mini-person-medium .env

log "--- Cerebras ---"
run_vd2 electronics-mini-cerebras       .env.cerebras
run_vd2 electronics-mini-specs-cerebras .env.cerebras

log "--- Regenerating plots ---"
mkdir -p data/experiments/plots
for BENCH in electronics-mini electronics-mini-specs electronics-mini-pdf \
             electronics-mini-person-short electronics-mini-person-medium; do
    "$PYTHON" scripts/vis-benchmark-fig.py "$BENCH" \
        --outprefix "data/experiments/plots/${BENCH}" || log "WARNING: vis failed for $BENCH"
done

log "ALL DONE."
