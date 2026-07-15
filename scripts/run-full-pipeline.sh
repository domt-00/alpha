#!/usr/bin/env bash
# Full end-to-end pipeline for the three electronics benchmarks.
# Runs sequentially to stay within API rate limits.
#
# Usage (from DT Study directory):
#   nohup bash scripts/run-full-pipeline.sh > logs/pipeline.log 2>&1 &
#   tail -f logs/pipeline.log

set -e
# Always run from the DT Study directory regardless of where the script is invoked
cd "$(dirname "$0")/.."
mkdir -p logs

# Use the project's venv Python
PYTHON="$(pwd)/venv/bin/python"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

# ── Shared proxy parameters ────────────────────────────────────────────────
CAP=20
MIN_ITER=0
CHECK="high"
TARGET="highest"
HAPPY="low"
EMPHASIS="Quickly explore the person's valuation and get to the essence of things"
ANCHOR="20 to 30"
NUM_Q=5

# ══════════════════════════════════════════════════════════════════════════
# STEP 1: Finish missing FullPersons for ELECTRONICS base benchmark
# ══════════════════════════════════════════════════════════════════════════
log "STEP 1: Finishing missing FullPersons for electronics benchmark"
"$PYTHON" scripts/make-missing-fullpersons.py --benchmark electronics
log "STEP 1 complete."

# ══════════════════════════════════════════════════════════════════════════
# STEP 2: Generate ELECTRONICS-SPECS benchmark
# ══════════════════════════════════════════════════════════════════════════
log "STEP 2: Generating electronics-specs benchmark"
"$PYTHON" scripts/make-benchmark-sequential.py \
    --benchmark electronics-specs \
    --scenarios ELECTRONICS-SPECS \
    --num_setups 3 \
    --num_people 3 \
    --sleep_between 5
log "STEP 2 complete."

# ══════════════════════════════════════════════════════════════════════════
# STEP 3: Generate ELECTRONICS-REVIEWS benchmark
# ══════════════════════════════════════════════════════════════════════════
log "STEP 3: Generating electronics-reviews benchmark"
"$PYTHON" scripts/make-benchmark-sequential.py \
    --benchmark electronics-reviews \
    --scenarios ELECTRONICS-REVIEWS \
    --num_setups 3 \
    --num_people 3 \
    --sleep_between 5
log "STEP 3 complete."

# ══════════════════════════════════════════════════════════════════════════
# STEP 4: Run all 5 proxies — ELECTRONICS base
# ══════════════════════════════════════════════════════════════════════════
log "STEP 4: Running proxies for electronics benchmark"

log "  Proxy-XOR: electronics"
"$PYTHON" scripts/run-proxy-xor.py --benchmark electronics

log "  Proxy-VD1: electronics"
"$PYTHON" scripts/run-proxy-vd1.py \
    --benchmark electronics \
    --cap $CAP --min_iterations $MIN_ITER \
    --check_priority "$CHECK" --target_bundle_priority "$TARGET" \
    --happy_priority "$HAPPY" --target_bundle_emphasis "$EMPHASIS" \
    --anchor_num_target_bundles "$ANCHOR"

log "  Proxy-VD2: electronics"
"$PYTHON" scripts/run-proxy-vd2.py \
    --benchmark electronics \
    --cap $CAP --min_iterations $MIN_ITER \
    --check_priority "$CHECK" --target_bundle_priority "$TARGET" \
    --happy_priority "$HAPPY" --target_bundle_emphasis "$EMPHASIS" \
    --anchor_num_target_bundles "$ANCHOR"

log "  Proxy-NVD: electronics"
"$PYTHON" scripts/run-proxy-nvd.py \
    --benchmark electronics \
    --num_questions $NUM_Q \
    --cap $CAP --min_iterations $MIN_ITER \
    --check_priority "$CHECK" --target_bundle_priority "$TARGET" \
    --happy_priority "$HAPPY" --target_bundle_emphasis "$EMPHASIS" \
    --anchor_num_target_bundles "$ANCHOR"

log "  Proxy-H: electronics"
"$PYTHON" scripts/run-proxy-h.py \
    --benchmark electronics \
    --cap $CAP --min_iterations $MIN_ITER \
    --check_priority "$CHECK" --target_bundle_priority "$TARGET" \
    --happy_priority "$HAPPY" --target_bundle_emphasis "$EMPHASIS" \
    --anchor_num_target_bundles "$ANCHOR"

log "STEP 4 complete."

# ══════════════════════════════════════════════════════════════════════════
# STEP 5: Run all 5 proxies — ELECTRONICS-SPECS
# ══════════════════════════════════════════════════════════════════════════
log "STEP 5: Running proxies for electronics-specs benchmark"

log "  Proxy-XOR: electronics-specs"
"$PYTHON" scripts/run-proxy-xor.py --benchmark electronics-specs

log "  Proxy-VD1: electronics-specs"
"$PYTHON" scripts/run-proxy-vd1.py \
    --benchmark electronics-specs \
    --cap $CAP --min_iterations $MIN_ITER \
    --check_priority "$CHECK" --target_bundle_priority "$TARGET" \
    --happy_priority "$HAPPY" --target_bundle_emphasis "$EMPHASIS" \
    --anchor_num_target_bundles "$ANCHOR"

log "  Proxy-VD2: electronics-specs"
"$PYTHON" scripts/run-proxy-vd2.py \
    --benchmark electronics-specs \
    --cap $CAP --min_iterations $MIN_ITER \
    --check_priority "$CHECK" --target_bundle_priority "$TARGET" \
    --happy_priority "$HAPPY" --target_bundle_emphasis "$EMPHASIS" \
    --anchor_num_target_bundles "$ANCHOR"

log "  Proxy-NVD: electronics-specs"
"$PYTHON" scripts/run-proxy-nvd.py \
    --benchmark electronics-specs \
    --num_questions $NUM_Q \
    --cap $CAP --min_iterations $MIN_ITER \
    --check_priority "$CHECK" --target_bundle_priority "$TARGET" \
    --happy_priority "$HAPPY" --target_bundle_emphasis "$EMPHASIS" \
    --anchor_num_target_bundles "$ANCHOR"

log "  Proxy-H: electronics-specs"
"$PYTHON" scripts/run-proxy-h.py \
    --benchmark electronics-specs \
    --cap $CAP --min_iterations $MIN_ITER \
    --check_priority "$CHECK" --target_bundle_priority "$TARGET" \
    --happy_priority "$HAPPY" --target_bundle_emphasis "$EMPHASIS" \
    --anchor_num_target_bundles "$ANCHOR"

log "STEP 5 complete."

# ══════════════════════════════════════════════════════════════════════════
# STEP 6: Run all 5 proxies — ELECTRONICS-REVIEWS
# ══════════════════════════════════════════════════════════════════════════
log "STEP 6: Running proxies for electronics-reviews benchmark"

log "  Proxy-XOR: electronics-reviews"
"$PYTHON" scripts/run-proxy-xor.py --benchmark electronics-reviews

log "  Proxy-VD1: electronics-reviews"
"$PYTHON" scripts/run-proxy-vd1.py \
    --benchmark electronics-reviews \
    --cap $CAP --min_iterations $MIN_ITER \
    --check_priority "$CHECK" --target_bundle_priority "$TARGET" \
    --happy_priority "$HAPPY" --target_bundle_emphasis "$EMPHASIS" \
    --anchor_num_target_bundles "$ANCHOR"

log "  Proxy-VD2: electronics-reviews"
"$PYTHON" scripts/run-proxy-vd2.py \
    --benchmark electronics-reviews \
    --cap $CAP --min_iterations $MIN_ITER \
    --check_priority "$CHECK" --target_bundle_priority "$TARGET" \
    --happy_priority "$HAPPY" --target_bundle_emphasis "$EMPHASIS" \
    --anchor_num_target_bundles "$ANCHOR"

log "  Proxy-NVD: electronics-reviews"
"$PYTHON" scripts/run-proxy-nvd.py \
    --benchmark electronics-reviews \
    --num_questions $NUM_Q \
    --cap $CAP --min_iterations $MIN_ITER \
    --check_priority "$CHECK" --target_bundle_priority "$TARGET" \
    --happy_priority "$HAPPY" --target_bundle_emphasis "$EMPHASIS" \
    --anchor_num_target_bundles "$ANCHOR"

log "  Proxy-H: electronics-reviews"
"$PYTHON" scripts/run-proxy-h.py \
    --benchmark electronics-reviews \
    --cap $CAP --min_iterations $MIN_ITER \
    --check_priority "$CHECK" --target_bundle_priority "$TARGET" \
    --happy_priority "$HAPPY" --target_bundle_emphasis "$EMPHASIS" \
    --anchor_num_target_bundles "$ANCHOR"

log "STEP 6 complete."

# ══════════════════════════════════════════════════════════════════════════
# STEP 7: Generate efficiency curve plots
# ══════════════════════════════════════════════════════════════════════════
log "STEP 7: Generating visualisations"
mkdir -p data/experiments/plots

for BENCH in electronics electronics-specs electronics-reviews; do
    log "  vis-benchmark-fig: $BENCH"
    "$PYTHON" scripts/vis-benchmark-fig.py "$BENCH" \
        --outprefix "data/experiments/plots/${BENCH}" || \
        log "  WARNING: vis-benchmark-fig failed for $BENCH (continuing)"
done

log "STEP 7 complete."
log "ALL DONE. Results in data/experiments/plots/"
