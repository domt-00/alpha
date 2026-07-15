#!/usr/bin/env bash
# Full pipeline using local Gemma 4 12B via Ollama.
# Runs all 5 proxies on three benchmarks (electronics-gemma, electronics-specs-gemma,
# electronics-reviews-gemma) and generates comparison plots.
#
# Prerequisites:
#   - Ollama running: `ollama serve` (or already running as a service)
#   - Gemma model pulled: `ollama pull gemma4:12b`
#
# Usage (from DT Study directory):
#   nohup bash scripts/run-gemma-pipeline.sh > logs/gemma-pipeline.log 2>&1 &
#   tail -f logs/gemma-pipeline.log

set -e
cd "$(dirname "$0")/.."
mkdir -p logs

PYTHON="$(pwd)/venv/bin/python"
ENV_PATH=".env.gemma"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

CAP=20
MIN_ITER=0
CHECK="high"
TARGET="highest"
HAPPY="low"
EMPHASIS="Quickly explore the person's valuation and get to the essence of things"
ANCHOR="20 to 30"
NUM_Q=5

log "Starting Gemma 4 12B pipeline (Ollama local inference)"
log "Using env: $ENV_PATH"

# ══════════════════════════════════════════════════════════════════════════
# STEP 1: Run all 5 proxies — ELECTRONICS-GEMMA
# ══════════════════════════════════════════════════════════════════════════
log "STEP 1: Running proxies for electronics-gemma benchmark"

log "  Proxy-XOR: electronics-gemma"
"$PYTHON" scripts/run-proxy-xor.py \
    --benchmark electronics-gemma \
    --env_path "$ENV_PATH"

log "  Proxy-VD1: electronics-gemma"
"$PYTHON" scripts/run-proxy-vd1.py \
    --benchmark electronics-gemma \
    --env_path "$ENV_PATH" \
    --cap $CAP --min_iterations $MIN_ITER \
    --check_priority "$CHECK" --target_bundle_priority "$TARGET" \
    --happy_priority "$HAPPY" --target_bundle_emphasis "$EMPHASIS" \
    --anchor_num_target_bundles "$ANCHOR"

log "  Proxy-VD2: electronics-gemma"
"$PYTHON" scripts/run-proxy-vd2.py \
    --benchmark electronics-gemma \
    --env_path "$ENV_PATH" \
    --cap $CAP --min_iterations $MIN_ITER \
    --check_priority "$CHECK" --target_bundle_priority "$TARGET" \
    --happy_priority "$HAPPY" --target_bundle_emphasis "$EMPHASIS" \
    --anchor_num_target_bundles "$ANCHOR"

log "  Proxy-NVD: electronics-gemma"
"$PYTHON" scripts/run-proxy-nvd.py \
    --benchmark electronics-gemma \
    --env_path "$ENV_PATH" \
    --num_questions $NUM_Q \
    --cap $CAP --min_iterations $MIN_ITER \
    --check_priority "$CHECK" --target_bundle_priority "$TARGET" \
    --happy_priority "$HAPPY" --target_bundle_emphasis "$EMPHASIS" \
    --anchor_num_target_bundles "$ANCHOR"

log "  Proxy-H: electronics-gemma"
"$PYTHON" scripts/run-proxy-h.py \
    --benchmark electronics-gemma \
    --env_path "$ENV_PATH" \
    --cap $CAP --min_iterations $MIN_ITER \
    --check_priority "$CHECK" --target_bundle_priority "$TARGET" \
    --happy_priority "$HAPPY" --target_bundle_emphasis "$EMPHASIS" \
    --anchor_num_target_bundles "$ANCHOR"

log "STEP 1 complete."

# ══════════════════════════════════════════════════════════════════════════
# STEP 2: Run all 5 proxies — ELECTRONICS-SPECS-GEMMA
# ══════════════════════════════════════════════════════════════════════════
log "STEP 2: Running proxies for electronics-specs-gemma benchmark"

log "  Proxy-XOR: electronics-specs-gemma"
"$PYTHON" scripts/run-proxy-xor.py \
    --benchmark electronics-specs-gemma \
    --env_path "$ENV_PATH"

log "  Proxy-VD1: electronics-specs-gemma"
"$PYTHON" scripts/run-proxy-vd1.py \
    --benchmark electronics-specs-gemma \
    --env_path "$ENV_PATH" \
    --cap $CAP --min_iterations $MIN_ITER \
    --check_priority "$CHECK" --target_bundle_priority "$TARGET" \
    --happy_priority "$HAPPY" --target_bundle_emphasis "$EMPHASIS" \
    --anchor_num_target_bundles "$ANCHOR"

log "  Proxy-VD2: electronics-specs-gemma"
"$PYTHON" scripts/run-proxy-vd2.py \
    --benchmark electronics-specs-gemma \
    --env_path "$ENV_PATH" \
    --cap $CAP --min_iterations $MIN_ITER \
    --check_priority "$CHECK" --target_bundle_priority "$TARGET" \
    --happy_priority "$HAPPY" --target_bundle_emphasis "$EMPHASIS" \
    --anchor_num_target_bundles "$ANCHOR"

log "  Proxy-NVD: electronics-specs-gemma"
"$PYTHON" scripts/run-proxy-nvd.py \
    --benchmark electronics-specs-gemma \
    --env_path "$ENV_PATH" \
    --num_questions $NUM_Q \
    --cap $CAP --min_iterations $MIN_ITER \
    --check_priority "$CHECK" --target_bundle_priority "$TARGET" \
    --happy_priority "$HAPPY" --target_bundle_emphasis "$EMPHASIS" \
    --anchor_num_target_bundles "$ANCHOR"

log "  Proxy-H: electronics-specs-gemma"
"$PYTHON" scripts/run-proxy-h.py \
    --benchmark electronics-specs-gemma \
    --env_path "$ENV_PATH" \
    --cap $CAP --min_iterations $MIN_ITER \
    --check_priority "$CHECK" --target_bundle_priority "$TARGET" \
    --happy_priority "$HAPPY" --target_bundle_emphasis "$EMPHASIS" \
    --anchor_num_target_bundles "$ANCHOR"

log "STEP 2 complete."

# ══════════════════════════════════════════════════════════════════════════
# STEP 3: Run all 5 proxies — ELECTRONICS-REVIEWS-GEMMA
# ══════════════════════════════════════════════════════════════════════════
log "STEP 3: Running proxies for electronics-reviews-gemma benchmark"

log "  Proxy-XOR: electronics-reviews-gemma"
"$PYTHON" scripts/run-proxy-xor.py \
    --benchmark electronics-reviews-gemma \
    --env_path "$ENV_PATH"

log "  Proxy-VD1: electronics-reviews-gemma"
"$PYTHON" scripts/run-proxy-vd1.py \
    --benchmark electronics-reviews-gemma \
    --env_path "$ENV_PATH" \
    --cap $CAP --min_iterations $MIN_ITER \
    --check_priority "$CHECK" --target_bundle_priority "$TARGET" \
    --happy_priority "$HAPPY" --target_bundle_emphasis "$EMPHASIS" \
    --anchor_num_target_bundles "$ANCHOR"

log "  Proxy-VD2: electronics-reviews-gemma"
"$PYTHON" scripts/run-proxy-vd2.py \
    --benchmark electronics-reviews-gemma \
    --env_path "$ENV_PATH" \
    --cap $CAP --min_iterations $MIN_ITER \
    --check_priority "$CHECK" --target_bundle_priority "$TARGET" \
    --happy_priority "$HAPPY" --target_bundle_emphasis "$EMPHASIS" \
    --anchor_num_target_bundles "$ANCHOR"

log "  Proxy-NVD: electronics-reviews-gemma"
"$PYTHON" scripts/run-proxy-nvd.py \
    --benchmark electronics-reviews-gemma \
    --env_path "$ENV_PATH" \
    --num_questions $NUM_Q \
    --cap $CAP --min_iterations $MIN_ITER \
    --check_priority "$CHECK" --target_bundle_priority "$TARGET" \
    --happy_priority "$HAPPY" --target_bundle_emphasis "$EMPHASIS" \
    --anchor_num_target_bundles "$ANCHOR"

log "  Proxy-H: electronics-reviews-gemma"
"$PYTHON" scripts/run-proxy-h.py \
    --benchmark electronics-reviews-gemma \
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

for BENCH in electronics-gemma electronics-specs-gemma electronics-reviews-gemma; do
    log "  vis-benchmark-fig: $BENCH"
    "$PYTHON" scripts/vis-benchmark-fig.py "$BENCH" \
        --outprefix "data/experiments/plots/${BENCH}" || \
        log "  WARNING: vis-benchmark-fig failed for $BENCH (continuing)"
done

log "STEP 4 complete."
log "ALL DONE. Gemma results in data/experiments/plots/"
