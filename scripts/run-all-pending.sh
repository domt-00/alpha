#!/usr/bin/env bash
# Run all pending Mistral work sequentially (low parallelism to avoid rate limits).
# Gemma is started in background simultaneously since it uses local Ollama (no API conflict).
#
# Usage (from DT Study directory):
#   nohup bash scripts/run-all-pending.sh > logs/run-all-pending.log 2>&1 &

cd "$(dirname "$0")/.."
mkdir -p logs

PYTHON="$(pwd)/venv/bin/python"
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

CAP=20; MIN_ITER=0; CHECK="high"; TARGET="highest"; HAPPY="low"
EMPHASIS="Quickly explore the person's valuation and get to the essence of things"
ANCHOR="20 to 30"
PAUSE=60

run_proxy() {
    local LABEL="$1"; local SCRIPT="$2"; local BENCH="$3"; local ENV="$4"
    shift 4
    log "  $LABEL — $BENCH"
    "$PYTHON" "$SCRIPT" --benchmark "$BENCH" --env_path "$ENV" \
        --cap $CAP --min_iterations $MIN_ITER \
        --check_priority "$CHECK" --target_bundle_priority "$TARGET" \
        --happy_priority "$HAPPY" --target_bundle_emphasis "$EMPHASIS" \
        --anchor_num_target_bundles "$ANCHOR" "$@" \
        || log "WARNING: $LABEL on $BENCH failed"
    log "  Pausing ${PAUSE}s..."
    sleep $PAUSE
}

log "======================================================"
log "Starting Gemma mini in background (local Ollama)"
log "======================================================"
ollama serve > /tmp/ollama.log 2>&1 &
sleep 5
nohup bash scripts/run-gemma-mini.sh >> logs/gemma-mini.log 2>&1 &
GEMMA_PID=$!
log "  Gemma PID: $GEMMA_PID"

log "======================================================"
log "=== 1. NVD fix re-runs (Mistral, bug fixed) ==="
log "======================================================"
run_proxy "NVD" scripts/run-proxy-nvd.py electronics-mini            .env --num_questions 5
run_proxy "NVD" scripts/run-proxy-nvd.py electronics-mini-specs-small .env --num_questions 5
run_proxy "NVD" scripts/run-proxy-nvd.py electronics-mini-pdf-small   .env --num_questions 5

log "======================================================"
log "=== 2. VD1 + VD2 small re-runs (specs + pdf, 1 setup 3 people) ==="
log "======================================================"
run_proxy "VD1" scripts/run-proxy-vd1.py electronics-mini-specs-small .env
run_proxy "VD2" scripts/run-proxy-vd2.py electronics-mini-specs-small .env
run_proxy "VD1" scripts/run-proxy-vd1.py electronics-mini-pdf-small   .env
run_proxy "VD2" scripts/run-proxy-vd2.py electronics-mini-pdf-small   .env

log "======================================================"
log "=== 3. Discount sensitivity — VD1 + VD2 on electronics-mini ==="
log "======================================================"
for DISCOUNT in 0.5 1.0; do
    log "  discount=$DISCOUNT"
    run_proxy "VD1" scripts/run-proxy-vd1.py electronics-mini .env --discount $DISCOUNT
    run_proxy "VD2" scripts/run-proxy-vd2.py electronics-mini .env --discount $DISCOUNT
done

log "======================================================"
log "ALL MISTRAL DONE. Waiting for Gemma (PID $GEMMA_PID)..."
log "======================================================"
wait $GEMMA_PID
pkill -f "ollama serve" 2>/dev/null
log "ALL DONE."
