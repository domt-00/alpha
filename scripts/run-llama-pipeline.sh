#!/usr/bin/env bash
# Full pipeline using Llama 3.3 70B via Groq API.
# Runs all 5 proxies on three benchmarks and generates comparison plots.
#
# Usage (from DT Study directory):
#   nohup bash scripts/run-llama-pipeline.sh > logs/llama-pipeline.log 2>&1 &
#   tail -f logs/llama-pipeline.log

set -e
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

log "Starting Llama 3.3 70B pipeline (Groq API)"
log "Using env: $ENV_PATH"

# ══════════════════════════════════════════════════════════════════════════
# STEP 1: Run all 5 proxies — ELECTRONICS-LLAMA
# ══════════════════════════════════════════════════════════════════════════
log "STEP 1: Running proxies for electronics-llama benchmark"

log "  Proxy-XOR: electronics-llama"
"$PYTHON" scripts/run-proxy-xor.py \
    --benchmark electronics-llama \
    --env_path "$ENV_PATH"

log "  Proxy-VD1: electronics-llama"
"$PYTHON" scripts/run-proxy-vd1.py \
    --benchmark electronics-llama \
    --env_path "$ENV_PATH" \
    --cap $CAP --min_iterations $MIN_ITER \
    --check_priority "$CHECK" --target_bundle_priority "$TARGET" \
    --happy_priority "$HAPPY" --target_bundle_emphasis "$EMPHASIS" \
    --anchor_num_target_bundles "$ANCHOR"

log "  Proxy-VD2: electronics-llama"
"$PYTHON" scripts/run-proxy-vd2.py \
    --benchmark electronics-llama \
    --env_path "$ENV_PATH" \
    --cap $CAP --min_iterations $MIN_ITER \
    --check_priority "$CHECK" --target_bundle_priority "$TARGET" \
    --happy_priority "$HAPPY" --target_bundle_emphasis "$EMPHASIS" \
    --anchor_num_target_bundles "$ANCHOR"

log "  Proxy-NVD: electronics-llama"
"$PYTHON" scripts/run-proxy-nvd.py \
    --benchmark electronics-llama \
    --env_path "$ENV_PATH" \
    --num_questions $NUM_Q \
    --cap $CAP --min_iterations $MIN_ITER \
    --check_priority "$CHECK" --target_bundle_priority "$TARGET" \
    --happy_priority "$HAPPY" --target_bundle_emphasis "$EMPHASIS" \
    --anchor_num_target_bundles "$ANCHOR"

log "  Proxy-H: electronics-llama"
"$PYTHON" scripts/run-proxy-h.py \
    --benchmark electronics-llama \
    --env_path "$ENV_PATH" \
    --cap $CAP --min_iterations $MIN_ITER \
    --check_priority "$CHECK" --target_bundle_priority "$TARGET" \
    --happy_priority "$HAPPY" --target_bundle_emphasis "$EMPHASIS" \
    --anchor_num_target_bundles "$ANCHOR"

log "STEP 1 complete."

# ══════════════════════════════════════════════════════════════════════════
# STEP 2: Run all 5 proxies — ELECTRONICS-SPECS-LLAMA
# ══════════════════════════════════════════════════════════════════════════
log "STEP 2: Running proxies for electronics-specs-llama benchmark"

log "  Proxy-XOR: electronics-specs-llama"
"$PYTHON" scripts/run-proxy-xor.py \
    --benchmark electronics-specs-llama \
    --env_path "$ENV_PATH"

log "  Proxy-VD1: electronics-specs-llama"
"$PYTHON" scripts/run-proxy-vd1.py \
    --benchmark electronics-specs-llama \
    --env_path "$ENV_PATH" \
    --cap $CAP --min_iterations $MIN_ITER \
    --check_priority "$CHECK" --target_bundle_priority "$TARGET" \
    --happy_priority "$HAPPY" --target_bundle_emphasis "$EMPHASIS" \
    --anchor_num_target_bundles "$ANCHOR"

log "  Proxy-VD2: electronics-specs-llama"
"$PYTHON" scripts/run-proxy-vd2.py \
    --benchmark electronics-specs-llama \
    --env_path "$ENV_PATH" \
    --cap $CAP --min_iterations $MIN_ITER \
    --check_priority "$CHECK" --target_bundle_priority "$TARGET" \
    --happy_priority "$HAPPY" --target_bundle_emphasis "$EMPHASIS" \
    --anchor_num_target_bundles "$ANCHOR"

log "  Proxy-NVD: electronics-specs-llama"
"$PYTHON" scripts/run-proxy-nvd.py \
    --benchmark electronics-specs-llama \
    --env_path "$ENV_PATH" \
    --num_questions $NUM_Q \
    --cap $CAP --min_iterations $MIN_ITER \
    --check_priority "$CHECK" --target_bundle_priority "$TARGET" \
    --happy_priority "$HAPPY" --target_bundle_emphasis "$EMPHASIS" \
    --anchor_num_target_bundles "$ANCHOR"

log "  Proxy-H: electronics-specs-llama"
"$PYTHON" scripts/run-proxy-h.py \
    --benchmark electronics-specs-llama \
    --env_path "$ENV_PATH" \
    --cap $CAP --min_iterations $MIN_ITER \
    --check_priority "$CHECK" --target_bundle_priority "$TARGET" \
    --happy_priority "$HAPPY" --target_bundle_emphasis "$EMPHASIS" \
    --anchor_num_target_bundles "$ANCHOR"

log "STEP 2 complete."

# ══════════════════════════════════════════════════════════════════════════
# STEP 3: Run all 5 proxies — ELECTRONICS-REVIEWS-LLAMA
# ══════════════════════════════════════════════════════════════════════════
log "STEP 3: Running proxies for electronics-reviews-llama benchmark"

log "  Proxy-XOR: electronics-reviews-llama"
"$PYTHON" scripts/run-proxy-xor.py \
    --benchmark electronics-reviews-llama \
    --env_path "$ENV_PATH"

log "  Proxy-VD1: electronics-reviews-llama"
"$PYTHON" scripts/run-proxy-vd1.py \
    --benchmark electronics-reviews-llama \
    --env_path "$ENV_PATH" \
    --cap $CAP --min_iterations $MIN_ITER \
    --check_priority "$CHECK" --target_bundle_priority "$TARGET" \
    --happy_priority "$HAPPY" --target_bundle_emphasis "$EMPHASIS" \
    --anchor_num_target_bundles "$ANCHOR"

log "  Proxy-VD2: electronics-reviews-llama"
"$PYTHON" scripts/run-proxy-vd2.py \
    --benchmark electronics-reviews-llama \
    --env_path "$ENV_PATH" \
    --cap $CAP --min_iterations $MIN_ITER \
    --check_priority "$CHECK" --target_bundle_priority "$TARGET" \
    --happy_priority "$HAPPY" --target_bundle_emphasis "$EMPHASIS" \
    --anchor_num_target_bundles "$ANCHOR"

log "  Proxy-NVD: electronics-reviews-llama"
"$PYTHON" scripts/run-proxy-nvd.py \
    --benchmark electronics-reviews-llama \
    --env_path "$ENV_PATH" \
    --num_questions $NUM_Q \
    --cap $CAP --min_iterations $MIN_ITER \
    --check_priority "$CHECK" --target_bundle_priority "$TARGET" \
    --happy_priority "$HAPPY" --target_bundle_emphasis "$EMPHASIS" \
    --anchor_num_target_bundles "$ANCHOR"

log "  Proxy-H: electronics-reviews-llama"
"$PYTHON" scripts/run-proxy-h.py \
    --benchmark electronics-reviews-llama \
    --env_path "$ENV_PATH" \
    --cap $CAP --min_iterations $MIN_ITER \
    --check_priority "$CHECK" --target_bundle_priority "$TARGET" \
    --happy_priority "$HAPPY" --target_bundle_emphasis "$EMPHASIS" \
    --anchor_num_target_bundles "$ANCHOR"

log "STEP 3 complete."

# ══════════════════════════════════════════════════════════════════════════
# STEP 4: Generate efficiency curve plots
# ══════════════════════════════════════════════════════════════════════════
log "STEP 4: Generating visualisations"
mkdir -p data/experiments/plots

for BENCH in electronics-llama electronics-specs-llama electronics-reviews-llama; do
    log "  vis-benchmark-fig: $BENCH"
    "$PYTHON" scripts/vis-benchmark-fig.py "$BENCH" \
        --outprefix "data/experiments/plots/${BENCH}" || \
        log "  WARNING: vis-benchmark-fig failed for $BENCH (continuing)"
done

log "STEP 4 complete."
log "ALL DONE. Llama results in data/experiments/plots/"
