#!/usr/bin/env bash
# Run VD1 (no discount), H, and NVD on electronics-specs-qwen with Qwen.
# XOR and VD1 (with discount) already ran — this replaces VD1 and adds H + NVD.
# VD2 skipped — too slow for 62-bundle enumeration on serial Qwen.
#
# Usage (from DT Study directory):
#   nohup bash scripts/run-specs-qwen-vd1-h-nvd.sh > logs/specs-qwen-vd1-h-nvd.log 2>&1 &
#   tail -f logs/specs-qwen-vd1-h-nvd.log

cd "$(dirname "$0")/.."
mkdir -p logs

PYTHON="$(pwd)/venv/bin/python"
ENV=".env.qwen"
BENCH="electronics-specs-qwen"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

CAP=20
MIN_ITER=0
MAX_ICA=10
NUM_Q=5
CHECK="high"
TARGET="highest"
HAPPY="low"
EMPHASIS="Quickly explore the person's valuation and get to the essence of things"
ANCHOR="20 to 30"

log "=== Electronics Specs Qwen — VD1 + H + NVD ==="
log "    Benchmark : $BENCH  (6 items, 3 setups)"
log "    Model     : qwen2.5:7b via Ollama"
log "    VD1 now uses face-value bids (no discount) matching original paper"
log ""

# ── 1. VD1 (no discount — fixed to match original paper) ─────────────────────
log "--- Step 1/3: VD1 (face-value, no discount) ---"
"$PYTHON" scripts/run-proxy-vd1.py \
    --benchmark "$BENCH" --env_path "$ENV" \
    --cap $CAP --min_iterations $MIN_ITER \
    --check_priority "$CHECK" \
    --target_bundle_priority "$TARGET" \
    --happy_priority "$HAPPY" \
    --target_bundle_emphasis "$EMPHASIS" \
    --anchor_num_target_bundles "$ANCHOR" \
    || { log "ERROR: VD1 failed"; exit 1; }
log "VD1 done."

# ── 2. H ─────────────────────────────────────────────────────────────────────
log "--- Step 2/3: H ---"
"$PYTHON" scripts/run-proxy-h.py \
    --benchmark "$BENCH" --env_path "$ENV" \
    --cap $CAP --min_iterations $MIN_ITER \
    --check_priority "$CHECK" \
    --target_bundle_priority "$TARGET" \
    --happy_priority "$HAPPY" \
    --target_bundle_emphasis "$EMPHASIS" \
    --anchor_num_target_bundles "$ANCHOR" \
    || { log "ERROR: H failed"; exit 1; }
log "H done."

# ── 3. NVD ───────────────────────────────────────────────────────────────────
log "--- Step 3/3: NVD  (has bundle enumeration — expect several hours) ---"
"$PYTHON" scripts/run-proxy-nvd.py \
    --benchmark "$BENCH" --env_path "$ENV" \
    --num_questions $NUM_Q \
    --cap $CAP --min_iterations $MIN_ITER --max_iterations $MAX_ICA \
    --check_priority "$CHECK" \
    --target_bundle_priority "$TARGET" \
    --happy_priority "$HAPPY" \
    --target_bundle_emphasis "$EMPHASIS" \
    --anchor_num_target_bundles "$ANCHOR" \
    || { log "ERROR: NVD failed"; exit 1; }
log "NVD done."

log "ALL DONE. Run: python scripts/build-run-registry.py --print"
