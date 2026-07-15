#!/usr/bin/env bash
# Run all 5 proxies on electronics-mini-gemma (3-item auction, Gemma 4 12B via Ollama).
# Compare timing vs Mistral electronics-mini results.
#
# Usage (from DT Study directory):
#   nohup bash scripts/run-gemma-mini.sh > logs/gemma-mini.log 2>&1 &

cd "$(dirname "$0")/.."
mkdir -p logs

PYTHON="$(pwd)/venv/bin/python"
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

BENCH="electronics-mini-gemma"
ENV=".env.gemma"
CAP=20; MIN_ITER=0; CHECK="high"; TARGET="highest"; HAPPY="low"
EMPHASIS="Quickly explore the person's valuation and get to the essence of things"
ANCHOR="20 to 30"

log "=== Gemma 4 12B — electronics-mini-gemma (3 items) ==="

log "--- Proxy-XOR ---"
START=$SECONDS
"$PYTHON" scripts/run-proxy-xor.py --benchmark "$BENCH" --env_path "$ENV" || log "WARNING: Proxy-XOR failed"
log "  Done in $(( SECONDS - START ))s"
sleep 30

log "--- Proxy-NVD ---"
START=$SECONDS
"$PYTHON" scripts/run-proxy-nvd.py --benchmark "$BENCH" --env_path "$ENV" \
    --num_questions 5 --cap $CAP --min_iterations $MIN_ITER \
    --check_priority "$CHECK" --target_bundle_priority "$TARGET" \
    --happy_priority "$HAPPY" --target_bundle_emphasis "$EMPHASIS" \
    --anchor_num_target_bundles "$ANCHOR" || log "WARNING: Proxy-NVD failed"
log "  Done in $(( SECONDS - START ))s"
sleep 30

log "--- Proxy-VD1 ---"
START=$SECONDS
"$PYTHON" scripts/run-proxy-vd1.py --benchmark "$BENCH" --env_path "$ENV" \
    --cap $CAP --min_iterations $MIN_ITER \
    --check_priority "$CHECK" --target_bundle_priority "$TARGET" \
    --happy_priority "$HAPPY" --target_bundle_emphasis "$EMPHASIS" \
    --anchor_num_target_bundles "$ANCHOR" || log "WARNING: Proxy-VD1 failed"
log "  Done in $(( SECONDS - START ))s"
sleep 30

log "--- Proxy-VD2 ---"
START=$SECONDS
"$PYTHON" scripts/run-proxy-vd2.py --benchmark "$BENCH" --env_path "$ENV" \
    --cap $CAP --min_iterations $MIN_ITER \
    --check_priority "$CHECK" --target_bundle_priority "$TARGET" \
    --happy_priority "$HAPPY" --target_bundle_emphasis "$EMPHASIS" \
    --anchor_num_target_bundles "$ANCHOR" || log "WARNING: Proxy-VD2 failed"
log "  Done in $(( SECONDS - START ))s"
sleep 30

log "--- Proxy-H ---"
START=$SECONDS
"$PYTHON" scripts/run-proxy-h.py --benchmark "$BENCH" --env_path "$ENV" \
    --cap $CAP --min_iterations $MIN_ITER \
    --check_priority "$CHECK" --target_bundle_priority "$TARGET" \
    --happy_priority "$HAPPY" --target_bundle_emphasis "$EMPHASIS" \
    --anchor_num_target_bundles "$ANCHOR" || log "WARNING: Proxy-H failed"
log "  Done in $(( SECONDS - START ))s"

log "ALL DONE. Logs in data/electronics-mini-gemma-logs/"
