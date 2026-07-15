#!/usr/bin/env bash
# Quick test of NVD-SR (self-routing) on Qwen — setup 0 only (3 people, 3 items).
# Compares against standard NVD on the same setup.
#
# Usage (from DT Study directory):
#   bash scripts/run-qwen-nvd-sr-test.sh 2>&1 | tee logs/nvd-sr-test.log

cd "$(dirname "$0")/.."
mkdir -p logs data/electronics-mini-qwen-sr-test-logs

PYTHON="$(pwd)/venv/bin/python"
ENV=".env.qwen"
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

CAP=20
MIN_ITER=3
MAX_ICA=15        # short cap for quick test
NUM_Q=5
CHECK="high"
TARGET="highest"
HAPPY="low"
EMPHASIS="Quickly explore the person's valuation and get to the essence of things"
ANCHOR="5 to 10"  # fewer anchors for speed

# Create a 1-setup test benchmark (setup 0 only)
BENCH="electronics-mini-qwen-sr-test"
mkdir -p "data/$BENCH"
if [ ! -L "data/$BENCH/ELECTRONICS-MINI" ]; then
    ln -sf "$(pwd)/data/electronics-mini/ELECTRONICS-MINI" "data/$BENCH/ELECTRONICS-MINI"
fi

log "=== NVD-SR test on Qwen (3 items, 3 people from setup 0, max_ica=$MAX_ICA) ==="

log "--- Standard NVD (baseline) ---"
"$PYTHON" scripts/run-proxy-nvd.py \
    --benchmark "$BENCH" --env_path "$ENV" \
    --num_questions $NUM_Q \
    --cap $CAP --min_iterations $MIN_ITER --max_iterations $MAX_ICA \
    --check_priority "$CHECK" --target_bundle_priority "$TARGET" \
    --happy_priority "$HAPPY" --target_bundle_emphasis "$EMPHASIS" \
    --anchor_num_target_bundles "$ANCHOR"

log "--- NVD-SR (self-routing) ---"
"$PYTHON" scripts/run-proxy-nvd-sr.py \
    --benchmark "$BENCH" --env_path "$ENV" \
    --num_questions $NUM_Q \
    --cap $CAP --min_iterations $MIN_ITER --max_iterations $MAX_ICA \
    --check_priority "$CHECK" --target_bundle_priority "$TARGET" \
    --happy_priority "$HAPPY" --target_bundle_emphasis "$EMPHASIS" \
    --anchor_num_target_bundles "$ANCHOR"

log "--- Comparison ---"
"$PYTHON" - <<'PYEOF'
import csv, glob

for label, pattern in [("NVD (standard)", "*NVD_*.csv"), ("NVD-SR", "*NVD-SR_*.csv")]:
    files = glob.glob(f"data/electronics-mini-qwen-sr-test-logs/{pattern}")
    if not files: print(f"{label}: no results"); continue
    rows = list(csv.DictReader(open(max(files))))
    if not rows: print(f"{label}: empty"); continue
    last = rows[-1]
    avg_hi = last.get("avg_human_interactions", "?")
    total_val = last.get("total_auction_value", "?")
    skipped = last.get("total_questions_skipped", "N/A")
    asked   = last.get("total_questions_asked",   "N/A")
    print(f"{label:20s}  welfare={total_val}  avg_interactions={avg_hi}  questions asked={asked} skipped={skipped}")
PYEOF

log "DONE. Full logs in data/electronics-mini-qwen-sr-test-logs/"
