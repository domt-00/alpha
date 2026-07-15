#!/usr/bin/env bash
# NVD efficiency pilot — compares NVD vs NVD-Restrict vs NVD-Prune vs NVD-R (both)
#
# Benchmark : electronics-mini-groq-sr-pilot (3 people, 1 setup, 3 items)
# Model     : gpt-oss-120b via Cerebras
# Purpose   : isolate the contribution of bundle restriction vs trend pruning
#
# Usage (from DT Study directory):
#   nohup bash scripts/run-nvd-r-pilot-cerebras.sh > logs/nvd-r-pilot-cerebras.log 2>&1 &
#   tail -f logs/nvd-r-pilot-cerebras.log

cd "$(dirname "$0")/.."
mkdir -p logs

PYTHON="$(pwd)/venv/bin/python"
ENV=".env.cerebras"
BENCH="electronics-mini-groq-sr-pilot"
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

CAP=20
MIN_ITER=5
MAX_ICA=10
NUM_Q=5
CHECK="high"
TARGET="highest"
HAPPY="low"
EMPHASIS="Quickly explore the person's valuation and get to the essence of things"
ANCHOR="20 to 30"
PRUNE=0.25
PAUSE=5
COMPRESS="--compress_description"   # ~75% token saving per value_query call

log "=== NVD Efficiency Pilot (Cerebras) ==="
log "    Benchmark  : $BENCH  (3 people, 1 setup, 3 items)"
log "    Model      : gpt-oss-120b via Cerebras"
log "    Variants   : NVD | NVD-Restrict | NVD-Prune | NVD-R (both)"
log "    prune_pct  : $PRUNE"
log "    Start      : $(date '+%Y-%m-%d %H:%M:%S')"
log ""

# ── 1. XOR baseline ──────────────────────────────────────────────────────────
log "--- Step 1: XOR baseline ---"
"$PYTHON" scripts/run-proxy-xor.py \
    --benchmark "$BENCH" --env_path "$ENV" \
    || { log "ERROR: XOR failed"; exit 1; }
sleep $PAUSE

# ── 2. NVD — reuse existing log if available ──────────────────────────────────
log "--- Step 2: NVD baseline ---"
NVD_LOG=$(ls -t data/${BENCH}-logs/log_Proxy-NVD_*.csv 2>/dev/null | head -1)
if [ -z "$NVD_LOG" ]; then
    log "No existing NVD log — running now..."
    "$PYTHON" scripts/run-proxy-nvd.py \
        --benchmark "$BENCH" --env_path "$ENV" \
        --num_questions $NUM_Q \
        --cap $CAP --min_iterations $MIN_ITER --max_iterations $MAX_ICA \
        --check_priority "$CHECK" --target_bundle_priority "$TARGET" \
        --happy_priority "$HAPPY" --target_bundle_emphasis "$EMPHASIS" \
        --anchor_num_target_bundles "$ANCHOR" $COMPRESS \
        || { log "ERROR: NVD failed"; exit 1; }
    sleep $PAUSE
else
    log "Reusing existing NVD log: $NVD_LOG"
fi

# ── 3. NVD-Restrict (bundle restriction only) ─────────────────────────────────
log "--- Step 3: NVD-Restrict (bundle restriction only, no pruning) ---"
"$PYTHON" scripts/run-proxy-nvd-restrict.py \
    --benchmark "$BENCH" --env_path "$ENV" \
    --num_questions $NUM_Q \
    --cap $CAP --min_iterations $MIN_ITER --max_iterations $MAX_ICA \
    --check_priority "$CHECK" --target_bundle_priority "$TARGET" \
    --happy_priority "$HAPPY" --target_bundle_emphasis "$EMPHASIS" \
    --anchor_num_target_bundles "$ANCHOR" $COMPRESS \
    || { log "ERROR: NVD-Restrict failed"; exit 1; }
sleep $PAUSE

# ── 4. NVD-Prune (trend pruning only) ────────────────────────────────────────
log "--- Step 4: NVD-Prune (trend pruning only, no restriction) ---"
"$PYTHON" scripts/run-proxy-nvd-prune.py \
    --benchmark "$BENCH" --env_path "$ENV" \
    --num_questions $NUM_Q \
    --cap $CAP --min_iterations $MIN_ITER --max_iterations $MAX_ICA \
    --check_priority "$CHECK" --target_bundle_priority "$TARGET" \
    --happy_priority "$HAPPY" --target_bundle_emphasis "$EMPHASIS" \
    --anchor_num_target_bundles "$ANCHOR" \
    --prune_percentile $PRUNE $COMPRESS \
    || { log "ERROR: NVD-Prune failed"; exit 1; }
sleep $PAUSE

# ── 5. NVD-R (restriction + pruning) ─────────────────────────────────────────
log "--- Step 5: NVD-R (bundle restriction + trend pruning) ---"
"$PYTHON" scripts/run-proxy-nvd-r.py \
    --benchmark "$BENCH" --env_path "$ENV" \
    --num_questions $NUM_Q \
    --cap $CAP --min_iterations $MIN_ITER --max_iterations $MAX_ICA \
    --check_priority "$CHECK" --target_bundle_priority "$TARGET" \
    --happy_priority "$HAPPY" --target_bundle_emphasis "$EMPHASIS" \
    --anchor_num_target_bundles "$ANCHOR" \
    --prune_percentile $PRUNE $COMPRESS \
    || { log "ERROR: NVD-R failed"; exit 1; }

# ── 6. Comparison table ───────────────────────────────────────────────────────
log "--- Comparison Table ---"
"$PYTHON" - <<'PYEOF'
import csv, glob

bench   = "electronics-mini-groq-sr-pilot"
log_dir = f"data/{bench}-logs"

def latest(prefix):
    files = sorted(glob.glob(f"{log_dir}/log_{prefix}_*.csv"))
    return files[-1] if files else None

def final_welfare(filepath):
    if not filepath: return None
    rows = list(csv.DictReader(open(filepath)))
    by_setup = {}
    for r in rows:
        by_setup[r.get("setup_index", "0")] = float(r["total_auction_value"])
    return list(by_setup.values())

def final_interactions(filepath):
    if not filepath: return None
    rows = list(csv.DictReader(open(filepath)))
    by_setup = {}
    for r in rows:
        by_setup[r.get("setup_index", "0")] = float(r.get("avg_human_interactions", 0) or 0)
    return list(by_setup.values())

variants = [
    ("NVD",          latest("Proxy-NVD")),
    ("NVD-Restrict", latest("Proxy-NVD-Restrict")),
    ("NVD-Prune",    latest("Proxy-NVD-Prune")),
    ("NVD-R",        latest("Proxy-NVD-R")),
]

xor_w = final_welfare(latest("Proxy-XOR"))

print()
print("=" * 80)
print(f"  NVD EFFICIENCY PILOT — {bench}")
print("=" * 80)
print(f"\n  XOR optimal: {xor_w[0] if xor_w else 'N/A'}\n")
print(f"  {'Variant':<16} {'Welfare':>8} {'Efficiency':>11} {'Avg Interactions':>18}")
print("  " + "-" * 56)

for name, filepath in variants:
    w = final_welfare(filepath)
    i = final_interactions(filepath)
    if w and xor_w:
        eff = w[0] / xor_w[0] * 100
        avg_i = f"{i[0]:.1f}" if i else "N/A"
        print(f"  {name:<16} {w[0]:>8.0f} {eff:>10.1f}% {avg_i:>18}")
    else:
        print(f"  {name:<16} {'N/A':>8}")

print()
print("=" * 80)
PYEOF

log "ALL DONE."
