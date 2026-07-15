#!/usr/bin/env bash
# Resumes the DeepSeek experiment from VD1 onwards (XOR already completed).
# Max 30 ICA iterations per setup — guarantees termination within ~15 min/proxy.
#
# Usage (from DT Study directory):
#   nohup bash scripts/run-deepseek-vd1-onwards.sh > logs/deepseek-experiment.log 2>&1 &
#   tail -f logs/deepseek-experiment.log

cd "$(dirname "$0")/.."
mkdir -p logs

PYTHON="$(pwd)/venv/bin/python"
ENV=".env.deepseek"
BENCH="electronics-mini-deepseek"
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

CAP=20
MIN_ITER=3
MAX_ICA=30
CHECK="high"
TARGET="highest"
HAPPY="low"
EMPHASIS="Quickly explore the person's valuation and get to the essence of things"
ANCHOR="20 to 30"
NUM_Q=5
PAUSE=15

START_TIME=$(date '+%Y-%m-%d %H:%M:%S')
log "=== DeepSeek-V3 experiment (VD1 onwards, max_ica=$MAX_ICA) ==="
log "    Benchmark : $BENCH (3 items, 9 people, 3 setups)"
log "    Model     : deepseek-chat (deepseek-V3)"
log "    Pricing   : \$0.27/M input | \$1.10/M output"
log "    Start     : $START_TIME"
log "    XOR       : already done — skipping"

run() {
    local LABEL="$1"; local SCRIPT="$2"; shift 2
    log "--- $LABEL ---"
    "$PYTHON" "$SCRIPT" --benchmark "$BENCH" --env_path "$ENV" "$@" \
        || log "WARNING: $LABEL failed"
    sleep $PAUSE
}

run "Proxy-VD1" scripts/run-proxy-vd1.py \
    --cap $CAP --min_iterations $MIN_ITER --max_iterations $MAX_ICA \
    --check_priority "$CHECK" --target_bundle_priority "$TARGET" \
    --happy_priority "$HAPPY" --target_bundle_emphasis "$EMPHASIS" \
    --anchor_num_target_bundles "$ANCHOR"

run "Proxy-VD2" scripts/run-proxy-vd2.py \
    --cap $CAP --min_iterations $MIN_ITER --max_iterations $MAX_ICA \
    --check_priority "$CHECK" --target_bundle_priority "$TARGET" \
    --happy_priority "$HAPPY" --target_bundle_emphasis "$EMPHASIS" \
    --anchor_num_target_bundles "$ANCHOR"

run "Proxy-NVD" scripts/run-proxy-nvd.py \
    --num_questions $NUM_Q \
    --cap $CAP --min_iterations $MIN_ITER --max_iterations $MAX_ICA \
    --check_priority "$CHECK" --target_bundle_priority "$TARGET" \
    --happy_priority "$HAPPY" --target_bundle_emphasis "$EMPHASIS" \
    --anchor_num_target_bundles "$ANCHOR"

run "Proxy-H" scripts/run-proxy-h.py \
    --cap $CAP --min_iterations $MIN_ITER --max_iterations $MAX_ICA \
    --check_priority "$CHECK" --target_bundle_priority "$TARGET" \
    --happy_priority "$HAPPY" --target_bundle_emphasis "$EMPHASIS" \
    --anchor_num_target_bundles "$ANCHOR"

log "--- Results ---"
ls -lh "data/${BENCH}-logs/"*.csv 2>/dev/null || log "No result files found."

log "--- Token & Cost Summary ---"
"$PYTHON" - <<PYEOF
import csv, os
from datetime import datetime

start = "$START_TIME"
csv_path = "logs/token-usage.csv"

if not os.path.exists(csv_path):
    print("No token-usage.csv found.")
else:
    with open(csv_path) as f:
        rows = list(csv.DictReader(f))

    ds_rows = [r for r in rows if r.get("provider") == "deepseek" and r.get("timestamp", "") >= start]

    prompt     = sum(int(r.get("prompt_tokens", 0) or 0) for r in ds_rows)
    completion = sum(int(r.get("completion_tokens", 0) or 0) for r in ds_rows)
    total      = prompt + completion
    cost       = sum(float(r.get("cost_usd", 0) or 0) for r in ds_rows)

    print(f"  API calls      : {len(ds_rows)}")
    print(f"  Prompt tokens  : {prompt:,}")
    print(f"  Output tokens  : {completion:,}")
    print(f"  Total tokens   : {total:,}")
    print(f"  Estimated cost : \${cost:.4f} USD")
PYEOF

log "ALL DONE. Results in data/${BENCH}-logs/"
