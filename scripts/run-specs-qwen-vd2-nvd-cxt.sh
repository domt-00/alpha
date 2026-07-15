#!/usr/bin/env bash
# Run VD2 then NVD on electronics-specs-qwen, CXT setup only (setup_index=0).
# Limits scope to 1 setup to keep runtime manageable on serial Qwen.
#
# Usage (from DT Study directory):
#   nohup bash scripts/run-specs-qwen-vd2-nvd-cxt.sh > logs/specs-qwen-vd2-nvd-cxt.log 2>&1 &
#   tail -f logs/specs-qwen-vd2-nvd-cxt.log

cd "$(dirname "$0")/.."
mkdir -p logs

PYTHON="$(pwd)/venv/bin/python"
ENV=".env.qwen"
BENCH="electronics-specs-qwen"
SETUP=0   # 0 = CXT

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

log "=== Electronics Specs Qwen — VD2 + NVD (CXT setup only) ==="
log "    Benchmark   : $BENCH"
log "    Setup index : $SETUP (CXT)"
log "    Model       : qwen2.5:7b via Ollama"
log ""

# ── 1. VD2 ───────────────────────────────────────────────────────────────────
log "--- Step 1/2: VD2 (discount=0.75, CXT only) ---"
"$PYTHON" scripts/run-proxy-vd2.py \
    --benchmark "$BENCH" --env_path "$ENV" \
    --setup_index $SETUP \
    --cap $CAP --min_iterations $MIN_ITER --max_iterations $MAX_ICA \
    --check_priority "$CHECK" \
    --target_bundle_priority "$TARGET" \
    --happy_priority "$HAPPY" \
    --target_bundle_emphasis "$EMPHASIS" \
    --anchor_num_target_bundles "$ANCHOR" \
    || { log "ERROR: VD2 failed"; exit 1; }
log "VD2 done."

# ── 2. NVD ───────────────────────────────────────────────────────────────────
log "--- Step 2/2: NVD (CXT only — bundle enumeration, expect several hours) ---"
"$PYTHON" scripts/run-proxy-nvd.py \
    --benchmark "$BENCH" --env_path "$ENV" \
    --setup_index $SETUP \
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
