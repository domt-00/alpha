#!/usr/bin/env bash
# NVD efficiency pilot — NVD vs NVD-Restrict vs NVD-Prune vs NVD-R on Qwen
#
# Benchmark : electronics-mini-groq-sr-pilot (3 people, 1 setup, 3 items)
# Model     : qwen2.5:7b via Ollama (local)
# Purpose   : validate NVD-R variants before Cerebras re-run
#
# Usage (from DT Study directory):
#   nohup bash scripts/run-nvd-r-pilot-qwen.sh > logs/nvd-r-pilot-qwen.log 2>&1 &
#   tail -f logs/nvd-r-pilot-qwen.log

cd "$(dirname "$0")/.."
mkdir -p logs

PYTHON="$(pwd)/venv/bin/python"
ENV=".env.qwen"
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

log "=== NVD Efficiency Pilot (Qwen) ==="
log "    Benchmark  : $BENCH  (3 people, 1 setup, 3 items)"
log "    Model      : qwen2.5:7b via Ollama"
log "    Variants   : NVD | NVD-Restrict | NVD-Prune | NVD-R (both)"
log "    Note       : Ollama runs requests serially — expect ~15-30 min total"
log ""

# ── 1. XOR baseline ──────────────────────────────────────────────────────────
log "--- Step 1: XOR baseline ---"
"$PYTHON" scripts/run-proxy-xor.py \
    --benchmark "$BENCH" --env_path "$ENV" \
    || { log "ERROR: XOR failed"; exit 1; }

# ── 2. NVD ───────────────────────────────────────────────────────────────────
log "--- Step 2: NVD ---"
"$PYTHON" scripts/run-proxy-nvd.py \
    --benchmark "$BENCH" --env_path "$ENV" \
    --num_questions $NUM_Q \
    --cap $CAP --min_iterations $MIN_ITER --max_iterations $MAX_ICA \
    --check_priority "$CHECK" --target_bundle_priority "$TARGET" \
    --happy_priority "$HAPPY" --target_bundle_emphasis "$EMPHASIS" \
    --anchor_num_target_bundles "$ANCHOR" \
    || { log "ERROR: NVD failed"; exit 1; }

# ── 3. NVD-Restrict ──────────────────────────────────────────────────────────
log "--- Step 3: NVD-Restrict (bundle restriction only) ---"
"$PYTHON" scripts/run-proxy-nvd-restrict.py \
    --benchmark "$BENCH" --env_path "$ENV" \
    --num_questions $NUM_Q \
    --cap $CAP --min_iterations $MIN_ITER --max_iterations $MAX_ICA \
    --check_priority "$CHECK" --target_bundle_priority "$TARGET" \
    --happy_priority "$HAPPY" --target_bundle_emphasis "$EMPHASIS" \
    --anchor_num_target_bundles "$ANCHOR" \
    || { log "ERROR: NVD-Restrict failed"; exit 1; }

# ── 4. NVD-Prune ─────────────────────────────────────────────────────────────
log "--- Step 4: NVD-Prune (trend pruning only) ---"
"$PYTHON" scripts/run-proxy-nvd-prune.py \
    --benchmark "$BENCH" --env_path "$ENV" \
    --num_questions $NUM_Q \
    --cap $CAP --min_iterations $MIN_ITER --max_iterations $MAX_ICA \
    --check_priority "$CHECK" --target_bundle_priority "$TARGET" \
    --happy_priority "$HAPPY" --target_bundle_emphasis "$EMPHASIS" \
    --anchor_num_target_bundles "$ANCHOR" \
    --prune_percentile $PRUNE \
    || { log "ERROR: NVD-Prune failed"; exit 1; }

# ── 5. NVD-R (both) ──────────────────────────────────────────────────────────
log "--- Step 5: NVD-R (restriction + pruning) ---"
"$PYTHON" scripts/run-proxy-nvd-r.py \
    --benchmark "$BENCH" --env_path "$ENV" \
    --num_questions $NUM_Q \
    --cap $CAP --min_iterations $MIN_ITER --max_iterations $MAX_ICA \
    --check_priority "$CHECK" --target_bundle_priority "$TARGET" \
    --happy_priority "$HAPPY" --target_bundle_emphasis "$EMPHASIS" \
    --anchor_num_target_bundles "$ANCHOR" \
    --prune_percentile $PRUNE \
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

def read_col(filepath, col, default=None):
    if not filepath: return None
    rows = list(csv.DictReader(open(filepath)))
    by_setup = {}
    for r in rows:
        val = r.get(col)
        if val not in (None, ""):
            try: by_setup[r.get("setup_index", "0")] = float(val)
            except: pass
    return list(by_setup.values()) or None

variants = [
    ("XOR",          latest("Proxy-XOR")),
    ("NVD",          latest("Proxy-NVD")),
    ("NVD-Restrict", latest("Proxy-NVD-Restrict")),
    ("NVD-Prune",    latest("Proxy-NVD-Prune")),
    ("NVD-R",        latest("Proxy-NVD-R")),
]

xor_w = read_col(latest("Proxy-XOR"), "total_auction_value")

print()
print("=" * 70)
print(f"  NVD EFFICIENCY PILOT — {bench}  (Qwen)")
print("=" * 70)
print(f"\n  XOR optimal: {xor_w[0] if xor_w else 'N/A'}\n")
print(f"  {'Variant':<16} {'Welfare':>8} {'Efficiency':>11} {'Avg Interactions':>18}")
print("  " + "-" * 56)

for name, fp in variants:
    w = read_col(fp, "total_auction_value")
    i = read_col(fp, "avg_human_interactions")
    if w and xor_w:
        eff = w[0] / xor_w[0] * 100
        avg_i = f"{i[0]:.1f}" if i else "N/A"
        print(f"  {name:<16} {w[0]:>8.0f} {eff:>10.1f}% {avg_i:>18}")
    else:
        print(f"  {name:<16} {'N/A':>8}")

print()
print("=" * 70)
PYEOF

log "ALL DONE."
