#!/usr/bin/env bash
# NVD-SR pilot experiment — Llama 3.1 8B via Groq
#
# Runs XOR baseline, plain NVD, and NVD-SR on a 3-person pilot setup.
# Outputs a comparison table so results are directly comparable.
#
# Benchmark : electronics-mini-groq-sr-pilot
#   Setup 0 : alicemartin, alicetaylor, edwardharris  (3 items, 8 bundles each)
# Model     : llama-3.1-8b-instant (Groq free tier)
# Purpose   : test whether NVD-SR skips questions without hurting efficiency
#
# Usage (from DT Study directory):
#   nohup bash scripts/run-nvd-sr-pilot.sh > logs/nvd-sr-pilot.log 2>&1 &
#   tail -f logs/nvd-sr-pilot.log

cd "$(dirname "$0")/.."
mkdir -p logs

PYTHON="$(pwd)/venv/bin/python"
ENV=".env.llama8b"
BENCH="electronics-mini-groq-sr-pilot"
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

# Shared proxy parameters (same as main study defaults)
CAP=20
MIN_ITER=3
MAX_ICA=10          # pilot cap — extend to 30 for full run
NUM_Q=5             # questions the proxy is allowed to ask (SR may skip some)
CHECK="high"
TARGET="highest"
HAPPY="low"
EMPHASIS="Quickly explore the person's valuation and get to the essence of things"
ANCHOR="20 to 30"
PAUSE=10

START_TIME=$(date '+%Y-%m-%d %H:%M:%S')
log "=== NVD-SR Pilot Experiment ==="
log "    Benchmark  : $BENCH  (3 people, 1 setup, 3 items)"
log "    Model      : llama-3.1-8b-instant via Groq"
log "    Env        : $ENV"
log "    num_q      : $NUM_Q  (NVD always asks all; NVD-SR routes each)"
log "    max_iter   : $MAX_ICA  (pilot cap, extend to 30 for full run)"
log "    Start      : $START_TIME"
log ""

# ── 1. XOR baseline (no LLM calls — reads pre-computed FullPerson table) ──────
log "--- Step 1: XOR baseline (instant, establishes optimal welfare) ---"
"$PYTHON" scripts/run-proxy-xor.py \
    --benchmark "$BENCH" --env_path "$ENV" \
    || { log "ERROR: XOR failed"; exit 1; }
sleep $PAUSE

# ── 2. Plain NVD (always asks all num_q questions) ────────────────────────────
log "--- Step 2: NVD (baseline — always asks $NUM_Q questions) ---"
"$PYTHON" scripts/run-proxy-nvd.py \
    --benchmark "$BENCH" --env_path "$ENV" \
    --num_questions $NUM_Q \
    --cap $CAP --min_iterations $MIN_ITER --max_iterations $MAX_ICA \
    --check_priority "$CHECK" --target_bundle_priority "$TARGET" \
    --happy_priority "$HAPPY" --target_bundle_emphasis "$EMPHASIS" \
    --anchor_num_target_bundles "$ANCHOR" \
    || { log "ERROR: NVD failed"; exit 1; }
sleep $PAUSE

# ── 3. NVD-SR (self-routing — may skip questions) ─────────────────────────────
log "--- Step 3: NVD-SR (self-routing — model decides whether to ask) ---"
"$PYTHON" scripts/run-proxy-nvd-sr.py \
    --benchmark "$BENCH" --env_path "$ENV" \
    --num_questions $NUM_Q \
    --cap $CAP --min_iterations $MIN_ITER --max_iterations $MAX_ICA \
    --check_priority "$CHECK" --target_bundle_priority "$TARGET" \
    --happy_priority "$HAPPY" --target_bundle_emphasis "$EMPHASIS" \
    --anchor_num_target_bundles "$ANCHOR" \
    || { log "ERROR: NVD-SR failed"; exit 1; }

# ── 4. Comparison table ───────────────────────────────────────────────────────
log "--- Comparison Table ---"
"$PYTHON" - <<'PYEOF'
import csv, glob, os, json

bench = "electronics-mini-groq-sr-pilot"
log_dir = f"data/{bench}-logs"

def latest(prefix):
    files = sorted(glob.glob(f"{log_dir}/log_{prefix}_*.csv"))
    return files[-1] if files else None

def read_welfare(filepath):
    if not filepath:
        return None
    rows = list(csv.DictReader(open(filepath)))
    return [float(r["total_auction_value"]) for r in rows]

def read_interactions(filepath):
    if not filepath:
        return None
    rows = list(csv.DictReader(open(filepath)))
    return [float(r.get("avg_human_interactions", 0) or 0) for r in rows]

def read_sr_stats(filepath):
    if not filepath:
        return None, None
    rows = list(csv.DictReader(open(filepath)))
    asked   = sum(int(r.get("total_questions_asked",   0) or 0) for r in rows)
    skipped = sum(int(r.get("total_questions_skipped", 0) or 0) for r in rows)
    return asked, skipped

xor_file  = latest("Proxy-XOR")
nvd_file  = latest("Proxy-NVD")
nvdsr_file= latest("Proxy-NVD-SR")

xor_welfare   = read_welfare(xor_file)
nvd_welfare   = read_welfare(nvd_file)
nvdsr_welfare = read_welfare(nvdsr_file)
nvd_int   = read_interactions(nvd_file)
nvdsr_int = read_interactions(nvdsr_file)
asked, skipped = read_sr_stats(nvdsr_file)

print()
print("=" * 65)
print(f"  NVD-SR PILOT — {bench}")
print("=" * 65)

if xor_welfare and nvd_welfare and nvdsr_welfare:
    print(f"\n{'Setup':<8} {'XOR Opt':>10} {'NVD':>10} {'NVD Eff%':>10} {'NVD-SR':>10} {'SR Eff%':>10}")
    print("-" * 65)
    for i, (xw, nw, sw) in enumerate(zip(xor_welfare, nvd_welfare, nvdsr_welfare)):
        nvd_eff  = (nw / xw * 100) if xw else 0
        nvdsr_eff = (sw / xw * 100) if xw else 0
        print(f"Setup {i}  {xw:>10.1f} {nw:>10.1f} {nvd_eff:>9.1f}% {sw:>10.1f} {nvdsr_eff:>9.1f}%")

    avg_xor   = sum(xor_welfare)   / len(xor_welfare)
    avg_nvd   = sum(nvd_welfare)   / len(nvd_welfare)
    avg_nvdsr = sum(nvdsr_welfare) / len(nvdsr_welfare)
    print("-" * 65)
    print(f"{'Average':<8} {avg_xor:>10.1f} {avg_nvd:>10.1f} {avg_nvd/avg_xor*100:>9.1f}% {avg_nvdsr:>10.1f} {avg_nvdsr/avg_xor*100:>9.1f}%")

print()
if nvd_int and nvdsr_int:
    avg_nvd_int   = sum(nvd_int)   / len(nvd_int)
    avg_nvdsr_int = sum(nvdsr_int) / len(nvdsr_int)
    print(f"  Avg interactions — NVD : {avg_nvd_int:.1f}  |  NVD-SR : {avg_nvdsr_int:.1f}")

if asked is not None:
    total = asked + skipped
    pct_asked   = 100 * asked   / total if total else 0
    pct_skipped = 100 * skipped / total if total else 0
    print(f"  SR routing (all people) — Asked: {asked}/{total} ({pct_asked:.0f}%)  Skipped: {skipped}/{total} ({pct_skipped:.0f}%)")

print()
print(f"  Log files in {log_dir}/")
print(f"  XOR   : {os.path.basename(xor_file)   if xor_file   else 'missing'}")
print(f"  NVD   : {os.path.basename(nvd_file)   if nvd_file   else 'missing'}")
print(f"  NVD-SR: {os.path.basename(nvdsr_file) if nvdsr_file else 'missing'}")
print("=" * 65)
PYEOF

log "ALL DONE. To extend to setups 1 & 2, copy their FullPersons into"
log "data/${BENCH}/ELECTRONICS-MINI/1/ and data/${BENCH}/ELECTRONICS-MINI/2/"
log "and re-run this script."
