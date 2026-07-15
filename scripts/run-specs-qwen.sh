#!/usr/bin/env bash
# Run all 5 base proxies on electronics-specs with Qwen (local Ollama).
#
# Benchmark : electronics-specs-qwen (ELECTRONICS-SPECS, 6 items, 3 setups, 3 persons each)
# Model     : qwen2.5:7b via Ollama (serial — ~22s/call)
# Purpose   : compare auction efficiency with richer spec descriptions vs standard descriptions
#
# Expected runtime:
#   XOR    : ~1 min
#   VD1/H  : ~30-60 min each
#   VD2    : ~30-60 min
#   NVD    : ~4-8 hrs  (63 bundles × 3 persons × 6 refreshes × 3 setups, serial)
#   Total  : ~6-10 hrs — run overnight
#
# Usage (from DT Study directory):
#   nohup bash scripts/run-specs-qwen.sh > logs/specs-qwen.log 2>&1 &
#   tail -f logs/specs-qwen.log

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

log "=== Electronics Specs — Qwen ==="
log "    Benchmark : $BENCH  (6 items, 3 setups, 3 persons each)"
log "    Model     : qwen2.5:7b via Ollama  (serial requests)"
log "    Proxies   : XOR | VD1 | VD2 | H | NVD"
log ""

# ── 1. XOR ───────────────────────────────────────────────────────────────────
log "--- Step 1/5: XOR ---"
"$PYTHON" scripts/run-proxy-xor.py \
    --benchmark "$BENCH" --env_path "$ENV" \
    || { log "ERROR: XOR failed"; exit 1; }
log "XOR done."

# ── 2. VD1 ───────────────────────────────────────────────────────────────────
log "--- Step 2/5: VD1 ---"
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

# ── 3. VD2 ───────────────────────────────────────────────────────────────────
log "--- Step 3/5: VD2 ---"
"$PYTHON" scripts/run-proxy-vd2.py \
    --benchmark "$BENCH" --env_path "$ENV" \
    --cap $CAP --min_iterations $MIN_ITER \
    --check_priority "$CHECK" \
    --target_bundle_priority "$TARGET" \
    --happy_priority "$HAPPY" \
    --target_bundle_emphasis "$EMPHASIS" \
    --anchor_num_target_bundles "$ANCHOR" \
    || { log "ERROR: VD2 failed"; exit 1; }
log "VD2 done."

# ── 4. H ─────────────────────────────────────────────────────────────────────
log "--- Step 4/5: H ---"
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

# ── 5. NVD ───────────────────────────────────────────────────────────────────
log "--- Step 5/5: NVD  (this is the long one — ~4-8 hrs) ---"
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

log "ALL DONE. Logs in data/${BENCH}-logs/"
log "Run:  python scripts/build-run-registry.py --print  to see results."
