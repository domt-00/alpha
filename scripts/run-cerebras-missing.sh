#!/usr/bin/env bash
# Runs all missing / previously-zero Cerebras results.
#
# What's covered:
#   1. Discount sensitivity: VD1 + VD2 at disc=0.5, 0.75, 1.0 on electronics-mini
#      (all prior VD2 results and VD1 disc=0.75 were zero due to min_iterations=0)
#   2. electronics-mini-cerebras: VD1, VD2, NVD rerun (zeros fixed)
#   3. electronics-specs-cerebras: full pipeline (never run)
#   4. electronics-reviews-cerebras: full pipeline (never run)
#   5. electronics-cerebras: VD2, NVD, H (XOR already done; VD1 also rerun)
#
# Key fix: min_iterations=3 prevents LLM from choosing HAPPY on iteration 1.
#
# Usage (from DT Study directory):
#   nohup bash scripts/run-cerebras-missing.sh > logs/cerebras-missing.log 2>&1 &
#   tail -f logs/cerebras-missing.log

cd "$(dirname "$0")/.."
mkdir -p logs

PYTHON="$(pwd)/venv/bin/python"
ENV=".env.cerebras"
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

CAP=20
MAX_ICA=30
MIN_ITER=3
CHECK="high"
TARGET="highest"
HAPPY="low"
EMPHASIS="Quickly explore the person's valuation and get to the essence of things"
ANCHOR="20 to 30"
NUM_Q=5
PAUSE=30   # seconds between proxy runs to avoid rate limits

run_vd1() {
    local BENCH="$1" DISC="${2:-0.75}"
    log "  VD1 disc=$DISC on $BENCH"
    "$PYTHON" scripts/run-proxy-vd1.py --benchmark "$BENCH" --env_path "$ENV" \
        --cap $CAP --min_iterations $MIN_ITER --max_iterations $MAX_ICA \
        --check_priority "$CHECK" --target_bundle_priority "$TARGET" \
        --happy_priority "$HAPPY" --target_bundle_emphasis "$EMPHASIS" \
        --anchor_num_target_bundles "$ANCHOR" --discount "$DISC" \
        || log "WARNING: VD1 disc=$DISC $BENCH failed"
    sleep $PAUSE
}

run_vd2() {
    local BENCH="$1" DISC="${2:-0.75}"
    log "  VD2 disc=$DISC on $BENCH"
    "$PYTHON" scripts/run-proxy-vd2.py --benchmark "$BENCH" --env_path "$ENV" \
        --cap $CAP --min_iterations $MIN_ITER --max_iterations $MAX_ICA \
        --check_priority "$CHECK" --target_bundle_priority "$TARGET" \
        --happy_priority "$HAPPY" --target_bundle_emphasis "$EMPHASIS" \
        --anchor_num_target_bundles "$ANCHOR" --discount "$DISC" \
        || log "WARNING: VD2 disc=$DISC $BENCH failed"
    sleep $PAUSE
}

run_nvd() {
    local BENCH="$1"
    log "  NVD on $BENCH"
    "$PYTHON" scripts/run-proxy-nvd.py --benchmark "$BENCH" --env_path "$ENV" \
        --num_questions $NUM_Q \
        --cap $CAP --min_iterations $MIN_ITER --max_iterations $MAX_ICA \
        --check_priority "$CHECK" --target_bundle_priority "$TARGET" \
        --happy_priority "$HAPPY" --target_bundle_emphasis "$EMPHASIS" \
        --anchor_num_target_bundles "$ANCHOR" \
        || log "WARNING: NVD $BENCH failed"
    sleep $PAUSE
}

run_xor() {
    local BENCH="$1"
    log "  XOR on $BENCH"
    "$PYTHON" scripts/run-proxy-xor.py --benchmark "$BENCH" --env_path "$ENV" \
        || log "WARNING: XOR $BENCH failed"
    sleep $PAUSE
}

run_h() {
    local BENCH="$1"
    log "  H on $BENCH"
    "$PYTHON" scripts/run-proxy-h.py --benchmark "$BENCH" --env_path "$ENV" \
        --cap $CAP --min_iterations $MIN_ITER --max_iterations $MAX_ICA \
        --check_priority "$CHECK" --target_bundle_priority "$TARGET" \
        --happy_priority "$HAPPY" --target_bundle_emphasis "$EMPHASIS" \
        --anchor_num_target_bundles "$ANCHOR" \
        || log "WARNING: H $BENCH failed"
    sleep $PAUSE
}

log "=== Cerebras missing runs — min_iterations=$MIN_ITER ==="

# ── 1. Discount sensitivity on electronics-mini ──────────────────────────────
log "--- [1/5] Discount sensitivity (electronics-mini, VD1 + VD2) ---"
for DISC in 0.5 0.75 1.0; do
    log "  discount = $DISC"
    run_vd1 "electronics-mini" "$DISC"
    run_vd2 "electronics-mini" "$DISC"
done

# ── 2. electronics-mini-cerebras: fix zero runs for VD1/VD2/NVD ──────────────
log "--- [2/5] electronics-mini-cerebras (VD1, VD2, NVD fix) ---"
run_vd1 "electronics-mini-cerebras"
run_vd2 "electronics-mini-cerebras"
run_nvd "electronics-mini-cerebras"

# ── 3. electronics-specs-cerebras: full pipeline ─────────────────────────────
log "--- [3/5] electronics-specs-cerebras (full pipeline) ---"
run_xor "electronics-specs-cerebras"
run_vd1 "electronics-specs-cerebras"
run_vd2 "electronics-specs-cerebras"
run_nvd "electronics-specs-cerebras"
run_h   "electronics-specs-cerebras"

# ── 4. electronics-reviews-cerebras: full pipeline ───────────────────────────
log "--- [4/5] electronics-reviews-cerebras (full pipeline) ---"
run_xor "electronics-reviews-cerebras"
run_vd1 "electronics-reviews-cerebras"
run_vd2 "electronics-reviews-cerebras"
run_nvd "electronics-reviews-cerebras"
run_h   "electronics-reviews-cerebras"

# ── 5. electronics-cerebras: missing proxies (XOR already done) ───────────────
log "--- [5/5] electronics-cerebras (VD1 rerun + VD2, NVD, H) ---"
run_vd1 "electronics-cerebras"
run_vd2 "electronics-cerebras"
run_nvd "electronics-cerebras"
run_h   "electronics-cerebras"

log "=== ALL DONE ==="
