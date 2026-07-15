#!/usr/bin/env bash
# Run after laptop restart to pick up all pending work.
# Order: Mistral fixes first (API, no GPU), then Gemma (local GPU).
#
# Usage (from DT Study directory):
#   nohup bash scripts/restart-tomorrow.sh > logs/restart-tomorrow.log 2>&1 &

cd "$(dirname "$0")/.."
mkdir -p logs

PYTHON="$(pwd)/venv/bin/python"
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

CAP=20; MIN_ITER=0; CHECK="high"; TARGET="highest"; HAPPY="low"
EMPHASIS="Quickly explore the person's valuation and get to the essence of things"
ANCHOR="20 to 30"

run_proxy() {
    local LABEL="$1"; local SCRIPT="$2"; local BENCH="$3"; local ENV="$4"
    shift 4
    log "  $LABEL on $BENCH"
    "$PYTHON" "$SCRIPT" --benchmark "$BENCH" --env_path "$ENV" \
        --cap $CAP --min_iterations $MIN_ITER \
        --check_priority "$CHECK" --target_bundle_priority "$TARGET" \
        --happy_priority "$HAPPY" --target_bundle_emphasis "$EMPHASIS" \
        --anchor_num_target_bundles "$ANCHOR" "$@" \
        || log "WARNING: $LABEL on $BENCH failed"
    log "  Waiting 90s..."
    sleep 90
}

# ─────────────────────────────────────────────
# 1. VD1 fix re-runs (Mistral) — specs and pdf were killed by restart
# ─────────────────────────────────────────────
log "=== VD1 fix re-runs (Mistral) ==="
run_proxy "VD1" scripts/run-proxy-vd1.py electronics-mini-specs .env
run_proxy "VD1" scripts/run-proxy-vd1.py electronics-mini-pdf    .env

# ─────────────────────────────────────────────
# 2. VD2 fix re-run for pdf (was 0, never successfully re-run)
# ─────────────────────────────────────────────
log "=== VD2 fix re-run (pdf) ==="
run_proxy "VD2" scripts/run-proxy-vd2.py electronics-mini-pdf .env

# ─────────────────────────────────────────────
# 3. NVD fix re-runs (bug fixed tonight — missing person seed + no retry)
# ─────────────────────────────────────────────
log "=== NVD fix re-runs (Mistral) ==="
run_proxy "NVD" scripts/run-proxy-nvd.py electronics-mini       .env --num_questions 5
run_proxy "NVD" scripts/run-proxy-nvd.py electronics-mini-specs .env --num_questions 5
run_proxy "NVD" scripts/run-proxy-nvd.py electronics-mini-pdf   .env --num_questions 5

# ─────────────────────────────────────────────
# 4. Discount sensitivity (VD1 + VD2 at 0.5 and 1.0 on electronics-mini)
# ─────────────────────────────────────────────
log "=== Discount sensitivity ==="
for DISCOUNT in 0.5 1.0; do
    log "  discount=$DISCOUNT"
    run_proxy "VD1" scripts/run-proxy-vd1.py electronics-mini .env --discount $DISCOUNT
    run_proxy "VD2" scripts/run-proxy-vd2.py electronics-mini .env --discount $DISCOUNT
done

# ─────────────────────────────────────────────
# 5. Gemma mini — all 5 proxies (runs after Mistral finishes, clean machine)
# ─────────────────────────────────────────────
log "=== Gemma 4 12B — electronics-mini-gemma ==="
ollama serve > /tmp/ollama.log 2>&1 &
sleep 5
bash scripts/run-gemma-mini.sh >> logs/gemma-mini.log 2>&1
pkill -f "ollama serve" 2>/dev/null

log "ALL DONE."
