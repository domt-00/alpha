#!/usr/bin/env bash
# DeepSeek-V3 — VD2 epsilon (discount) sensitivity: 0.5, 0.75, 1.0
# Reuses existing electronics-deepseek FullPersons.
#
# Usage (from DT Study directory):
#   nohup bash scripts/run-deepseek-epsilon.sh > logs/deepseek-epsilon.log 2>&1 &
#   tail -f logs/deepseek-epsilon.log

cd "$(dirname "$0")/.."
mkdir -p logs

PYTHON="$(pwd)/venv/bin/python"
ENV=".env.deepseek"
BENCH="electronics-deepseek"
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

CAP=20
MIN_ITER=3
MAX_ICA=30
CHECK="high"
TARGET="highest"
HAPPY="low"
EMPHASIS="Quickly explore the person's valuation and get to the essence of things"
ANCHOR="20 to 30"
PAUSE=15

START_TIME=$(date '+%Y-%m-%d %H:%M:%S')
log "=== DeepSeek-V3 — VD2 epsilon sensitivity ==="
log "    Benchmark : $BENCH"
log "    Discounts : 0.5, 0.75, 1.0"
log "    Model     : deepseek-chat (DeepSeek-V3)"
log "    Pricing   : \$0.27/M input | \$1.10/M output"
log "    Start     : $START_TIME"

for DISCOUNT in 0.5 0.75 1.0; do
    log "--- VD2 discount=${DISCOUNT} ---"
    "$PYTHON" scripts/run-proxy-vd2.py \
        --benchmark "$BENCH" --env_path "$ENV" \
        --cap $CAP --min_iterations $MIN_ITER --max_iterations $MAX_ICA \
        --check_priority "$CHECK" --target_bundle_priority "$TARGET" \
        --happy_priority "$HAPPY" --target_bundle_emphasis "$EMPHASIS" \
        --anchor_num_target_bundles "$ANCHOR" \
        --discount $DISCOUNT \
        || log "WARNING: VD2 discount=${DISCOUNT} failed"
    sleep $PAUSE
done

log "--- Results ---"
ls -lh "data/${BENCH}-logs/"*VD2*.csv 2>/dev/null || log "No VD2 result files found."

log "--- Token & Cost Summary ---"
"$PYTHON" - <<PYEOF
import csv, os

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
    cost       = sum(float(r.get("cost_usd", 0) or 0) for r in ds_rows)
    print(f"  API calls      : {len(ds_rows)}")
    print(f"  Prompt tokens  : {prompt:,}")
    print(f"  Output tokens  : {completion:,}")
    print(f"  Estimated cost : \${cost:.4f} USD")
PYEOF

log "ALL DONE. Results in data/${BENCH}-logs/"
