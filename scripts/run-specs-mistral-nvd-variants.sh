#!/usr/bin/env bash
# Run NVD-Restrict, NVD-Prune, NVD-SR on electronics-specs-mistral-v2 with Mistral.
# Uses the same benchmark/logs folder as run-specs-mistral-all-fixed.sh so all
# Mistral results for electronics-specs live in one place, differentiated by
# proxy name in the log filename (log_Proxy-NVD-Restrict_*, etc).
#
# min_iterations=3 (not 0) — see run-specs-mistral-all-fixed.sh for why.
#
# Usage (from DT Study directory):
#   nohup bash scripts/run-specs-mistral-nvd-variants.sh > logs/specs-mistral-nvd-variants.log 2>&1 &
#   tail -f logs/specs-mistral-nvd-variants.log

cd "$(dirname "$0")/.."
mkdir -p logs

PYTHON="$(pwd)/venv/bin/python"
ENV=".env.mistral"
BENCH="electronics-specs-mistral-v2"

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

log "=== Electronics Specs — Mistral — NVD-Restrict, NVD-Prune, NVD-SR ==="
log "    Benchmark : $BENCH  (6 items, 3 setups)"
log "    min_iterations = $MIN_ITER"
log "    Logs      : data/${BENCH}-logs/"
log ""

# ── 1. NVD-Restrict ───────────────────────────────────────────────────────────
T0=$(date +%s)
log "--- Step 1/3: NVD-Restrict ---"
"$PYTHON" scripts/run-proxy-nvd-restrict.py \
    --benchmark "$BENCH" --env_path "$ENV" \
    --num_questions $NUM_Q \
    --cap $CAP --min_iterations $MIN_ITER --max_iterations $MAX_ICA \
    --check_priority "$CHECK" \
    --target_bundle_priority "$TARGET" \
    --happy_priority "$HAPPY" \
    --target_bundle_emphasis "$EMPHASIS" \
    --anchor_num_target_bundles "$ANCHOR" \
    || { log "ERROR: NVD-Restrict failed"; exit 1; }
T1=$(date +%s)
log "NVD-Restrict done in $((T1-T0))s."

# ── 2. NVD-Prune ─────────────────────────────────────────────────────────────
log "--- Step 2/3: NVD-Prune ---"
"$PYTHON" scripts/run-proxy-nvd-prune.py \
    --benchmark "$BENCH" --env_path "$ENV" \
    --num_questions $NUM_Q \
    --cap $CAP --min_iterations $MIN_ITER --max_iterations $MAX_ICA \
    --check_priority "$CHECK" \
    --target_bundle_priority "$TARGET" \
    --happy_priority "$HAPPY" \
    --target_bundle_emphasis "$EMPHASIS" \
    --anchor_num_target_bundles "$ANCHOR" \
    || { log "ERROR: NVD-Prune failed"; exit 1; }
T2=$(date +%s)
log "NVD-Prune done in $((T2-T1))s."

# ── 3. NVD-SR ────────────────────────────────────────────────────────────────
log "--- Step 3/3: NVD-SR ---"
"$PYTHON" scripts/run-proxy-nvd-sr.py \
    --benchmark "$BENCH" --env_path "$ENV" \
    --num_questions $NUM_Q \
    --cap $CAP --min_iterations $MIN_ITER --max_iterations $MAX_ICA \
    --check_priority "$CHECK" \
    --target_bundle_priority "$TARGET" \
    --happy_priority "$HAPPY" \
    --target_bundle_emphasis "$EMPHASIS" \
    --anchor_num_target_bundles "$ANCHOR" \
    || { log "ERROR: NVD-SR failed"; exit 1; }
T3=$(date +%s)
log "NVD-SR done in $((T3-T2))s."

log ""
log "=== ALL DONE ==="
log "NVD-Restrict: $((T1-T0))s | NVD-Prune: $((T2-T1))s | NVD-SR: $((T3-T2))s | TOTAL: $((T3-T0))s"
log "Run: python scripts/build-run-registry.py --print"
