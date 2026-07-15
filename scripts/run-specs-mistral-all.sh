#!/usr/bin/env bash
# Run VD1, VD2, H, NVD on electronics-specs with Mistral (mistral-small-latest).
# XOR baseline already exists (LLM-free, provider-independent) — not re-run.
#
# Usage (from DT Study directory):
#   nohup bash scripts/run-specs-mistral-all.sh > logs/specs-mistral-all.log 2>&1 &
#   tail -f logs/specs-mistral-all.log

cd "$(dirname "$0")/.."
mkdir -p logs

PYTHON="$(pwd)/venv/bin/python"
ENV=".env.mistral"
BENCH="electronics-specs-mistral"

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

log "=== Electronics Specs — Mistral (mistral-small-latest) — XOR, VD1, VD2, H, NVD ==="
log "    Benchmark : $BENCH  (6 items, 3 setups)"
log "    Logs      : data/${BENCH}-logs/  (separate from data/electronics-specs-logs/)"
log ""

# ── 0. XOR (LLM-free, but re-run here for a self-contained log folder) ───────
TSTART=$(date +%s)
log "--- Step 0/4: XOR ---"
"$PYTHON" scripts/run-proxy-xor.py \
    --benchmark "$BENCH" --env_path "$ENV" \
    || { log "ERROR: XOR failed"; exit 1; }
log "XOR done in $(($(date +%s)-TSTART))s."

# ── 1. VD1 ───────────────────────────────────────────────────────────────────
T0=$(date +%s)
log "--- Step 1/4: VD1 ---"
"$PYTHON" scripts/run-proxy-vd1.py \
    --benchmark "$BENCH" --env_path "$ENV" \
    --cap $CAP --min_iterations $MIN_ITER \
    --check_priority "$CHECK" \
    --target_bundle_priority "$TARGET" \
    --happy_priority "$HAPPY" \
    --target_bundle_emphasis "$EMPHASIS" \
    --anchor_num_target_bundles "$ANCHOR" \
    || { log "ERROR: VD1 failed"; exit 1; }
T1=$(date +%s)
log "VD1 done in $((T1-T0))s."

# ── 2. VD2 ───────────────────────────────────────────────────────────────────
log "--- Step 2/4: VD2 ---"
"$PYTHON" scripts/run-proxy-vd2.py \
    --benchmark "$BENCH" --env_path "$ENV" \
    --cap $CAP --min_iterations $MIN_ITER --max_iterations $MAX_ICA \
    --check_priority "$CHECK" \
    --target_bundle_priority "$TARGET" \
    --happy_priority "$HAPPY" \
    --target_bundle_emphasis "$EMPHASIS" \
    --anchor_num_target_bundles "$ANCHOR" \
    || { log "ERROR: VD2 failed"; exit 1; }
T2=$(date +%s)
log "VD2 done in $((T2-T1))s."

# ── 3. H ─────────────────────────────────────────────────────────────────────
log "--- Step 3/4: H ---"
"$PYTHON" scripts/run-proxy-h.py \
    --benchmark "$BENCH" --env_path "$ENV" \
    --cap $CAP --min_iterations $MIN_ITER \
    --check_priority "$CHECK" \
    --target_bundle_priority "$TARGET" \
    --happy_priority "$HAPPY" \
    --target_bundle_emphasis "$EMPHASIS" \
    --anchor_num_target_bundles "$ANCHOR" \
    || { log "ERROR: H failed"; exit 1; }
T3=$(date +%s)
log "H done in $((T3-T2))s."

# ── 4. NVD ───────────────────────────────────────────────────────────────────
log "--- Step 4/4: NVD ---"
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
T4=$(date +%s)
log "NVD done in $((T4-T3))s."

log ""
log "=== ALL DONE ==="
log "VD1: $((T1-T0))s | VD2: $((T2-T1))s | H: $((T3-T2))s | NVD: $((T4-T3))s | TOTAL: $((T4-T0))s"
log "Run: python scripts/build-run-registry.py --print"
