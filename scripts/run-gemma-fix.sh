#!/usr/bin/env bash
# Re-run NVD/VD1/VD2 on electronics-mini-gemma-small with two key fixes:
#   1. Ollama is started fresh before each proxy (was crashing between runs).
#   2. min_iterations=3 so Gemma can't say HAPPY on the very first call.
#
# Skips XOR and H — they already have good results.
# Uses 3-person/1-setup small benchmark for a quick sanity check.
#
# Usage (from DT Study directory):
#   nohup bash scripts/run-gemma-fix.sh > logs/gemma-fix.log 2>&1 &

cd "$(dirname "$0")/.."
mkdir -p logs

PYTHON="$(pwd)/venv/bin/python"
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

BENCH="electronics-mini-gemma-small"
ENV=".env.gemma"
CAP=20; MIN_ITER=3; CHECK="high"; TARGET="highest"; HAPPY="low"
EMPHASIS="Quickly explore the person's valuation and get to the essence of things"
ANCHOR="3 to 5"

start_ollama() {
    log "  Starting Ollama..."
    pkill -f "ollama serve" 2>/dev/null; sleep 3
    ollama serve > /tmp/ollama-fix.log 2>&1 &
    OLLAMA_PID=$!
    # Wait until Ollama is accepting connections
    for i in $(seq 1 30); do
        if curl -sf http://localhost:11434/ > /dev/null 2>&1; then
            log "  Ollama ready (${i}s)"
            return
        fi
        sleep 1
    done
    log "  WARNING: Ollama may not be ready"
}

stop_ollama() {
    log "  Stopping Ollama..."
    pkill -f "ollama serve" 2>/dev/null
    sleep 3
}

run_proxy() {
    local LABEL="$1"; local SCRIPT="$2"; shift 2
    log "--- $LABEL ---"
    START=$SECONDS
    start_ollama
    "$PYTHON" "$SCRIPT" --benchmark "$BENCH" --env_path "$ENV" \
        --cap $CAP --min_iterations $MIN_ITER \
        --check_priority "$CHECK" --target_bundle_priority "$TARGET" \
        --happy_priority "$HAPPY" --target_bundle_emphasis "$EMPHASIS" \
        --anchor_num_target_bundles "$ANCHOR" "$@" || log "WARNING: $LABEL failed"
    log "  Done in $(( SECONDS - START ))s"
    stop_ollama
    sleep 10
}

log "=== Gemma fix run — electronics-mini-gemma-small (3 persons, 1 setup) ==="
log "    Fixes: Ollama restarted per proxy; min_iterations=3"

run_proxy "Proxy-VD1" scripts/run-proxy-vd1.py
run_proxy "Proxy-VD2" scripts/run-proxy-vd2.py
run_proxy "Proxy-NVD" scripts/run-proxy-nvd.py --num_questions 5

log "ALL DONE. Logs in data/electronics-mini-gemma-small-logs/ (if exists) or electronics-mini-gemma-logs/"
log "Check CSVs for non-zero total_auction_value."
