#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/.."
PYTHON="$(pwd)/venv/bin/python"
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

log "Re-running Proxy-VD2 for electronics-reviews"
"$PYTHON" scripts/run-proxy-vd2.py \
    --benchmark electronics-reviews \
    --cap 20 --min_iterations 0 \
    --check_priority "high" \
    --target_bundle_priority "highest" \
    --happy_priority "low" \
    --target_bundle_emphasis "Quickly explore the person's valuation and get to the essence of things" \
    --anchor_num_target_bundles "20 to 30"

log "Regenerating plot..."
"$PYTHON" scripts/vis-benchmark-fig.py "electronics-reviews" \
    --outprefix "data/experiments/plots/electronics-reviews"
log "ALL DONE"
