#!/usr/bin/env bash
# Mistral — reviews benchmark (5 base proxies) + NVD-Ensemble + NVD-Active
# on electronics-specs-mistral-v2, run sequentially to avoid overlapping
# rate-limit load. All use min_iterations=3 (the fixed value).
#
# Usage (from DT Study directory):
#   nohup caffeinate -dis bash scripts/run-specs-mistral-newvariants.sh > logs/specs-mistral-newvariants.log 2>&1 &
#   tail -f logs/specs-mistral-newvariants.log

cd "$(dirname "$0")/.."
mkdir -p logs

PYTHON="$(pwd)/venv/bin/python"
ENV=".env.mistral"
SPECS_BENCH="electronics-specs-mistral-v2"
REVIEWS_BENCH="electronics-reviews-mistral"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

CAP=20
MIN_ITER=3
MAX_ICA=10
NUM_Q=5
CHECK="high"
TARGET="highest"
HAPPY="low"
EMPHASIS="Quickly explore the person's valuation and get to the essence of things"
ANCHOR="20 to 30"

log "=== Mistral — Reviews suite + NVD-Ensemble + NVD-Active ==="
log ""

# ── Part 1: Reviews benchmark, 5 base proxies ────────────────────────────────
log "--- Reviews 1/5: XOR ---"
T0=$(date +%s)
"$PYTHON" scripts/run-proxy-xor.py --benchmark "$REVIEWS_BENCH" --env_path "$ENV" \
    || log "ERROR: reviews XOR failed"
log "reviews XOR done in $(( $(date +%s) - T0 ))s."

log "--- Reviews 2/5: VD1 ---"
T0=$(date +%s)
"$PYTHON" scripts/run-proxy-vd1.py --benchmark "$REVIEWS_BENCH" --env_path "$ENV" \
    --cap $CAP --min_iterations $MIN_ITER \
    --check_priority "$CHECK" --target_bundle_priority "$TARGET" --happy_priority "$HAPPY" \
    --target_bundle_emphasis "$EMPHASIS" --anchor_num_target_bundles "$ANCHOR" \
    || log "ERROR: reviews VD1 failed"
log "reviews VD1 done in $(( $(date +%s) - T0 ))s."

log "--- Reviews 3/5: VD2 ---"
T0=$(date +%s)
"$PYTHON" scripts/run-proxy-vd2.py --benchmark "$REVIEWS_BENCH" --env_path "$ENV" \
    --cap $CAP --min_iterations $MIN_ITER --max_iterations $MAX_ICA \
    --check_priority "$CHECK" --target_bundle_priority "$TARGET" --happy_priority "$HAPPY" \
    --target_bundle_emphasis "$EMPHASIS" --anchor_num_target_bundles "$ANCHOR" \
    || log "ERROR: reviews VD2 failed"
log "reviews VD2 done in $(( $(date +%s) - T0 ))s."

log "--- Reviews 4/5: H ---"
T0=$(date +%s)
"$PYTHON" scripts/run-proxy-h.py --benchmark "$REVIEWS_BENCH" --env_path "$ENV" \
    --cap $CAP --min_iterations $MIN_ITER \
    --check_priority "$CHECK" --target_bundle_priority "$TARGET" --happy_priority "$HAPPY" \
    --target_bundle_emphasis "$EMPHASIS" --anchor_num_target_bundles "$ANCHOR" \
    || log "ERROR: reviews H failed"
log "reviews H done in $(( $(date +%s) - T0 ))s."

log "--- Reviews 5/5: NVD ---"
T0=$(date +%s)
"$PYTHON" scripts/run-proxy-nvd.py --benchmark "$REVIEWS_BENCH" --env_path "$ENV" \
    --num_questions $NUM_Q --cap $CAP --min_iterations $MIN_ITER --max_iterations $MAX_ICA \
    --check_priority "$CHECK" --target_bundle_priority "$TARGET" --happy_priority "$HAPPY" \
    --target_bundle_emphasis "$EMPHASIS" --anchor_num_target_bundles "$ANCHOR" \
    || log "ERROR: reviews NVD failed"
log "reviews NVD done in $(( $(date +%s) - T0 ))s."

# ── Part 2: NVD-Ensemble and NVD-Active on specs ─────────────────────────────
log "--- NVD-Ensemble (specs) ---"
T0=$(date +%s)
"$PYTHON" scripts/run-proxy-nvd-ensemble.py --benchmark "$SPECS_BENCH" --env_path "$ENV" \
    --num_questions $NUM_Q --cap $CAP --min_iterations $MIN_ITER --max_iterations $MAX_ICA \
    --check_priority "$CHECK" --target_bundle_priority "$TARGET" --happy_priority "$HAPPY" \
    --target_bundle_emphasis "$EMPHASIS" --anchor_num_target_bundles "$ANCHOR" \
    --ensemble_size 3 \
    || log "ERROR: NVD-Ensemble failed"
log "NVD-Ensemble done in $(( $(date +%s) - T0 ))s."

log "--- NVD-Active (specs) ---"
T0=$(date +%s)
"$PYTHON" scripts/run-proxy-nvd-active.py --benchmark "$SPECS_BENCH" --env_path "$ENV" \
    --num_questions $NUM_Q --cap $CAP --min_iterations $MIN_ITER --max_iterations $MAX_ICA \
    --check_priority "$CHECK" --target_bundle_priority "$TARGET" --happy_priority "$HAPPY" \
    --target_bundle_emphasis "$EMPHASIS" --anchor_num_target_bundles "$ANCHOR" \
    || log "ERROR: NVD-Active failed"
log "NVD-Active done in $(( $(date +%s) - T0 ))s."

log ""
log "=== ALL DONE ==="
log "Run: python scripts/build-run-registry.py --print"
