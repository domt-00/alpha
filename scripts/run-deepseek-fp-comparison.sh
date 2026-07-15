#!/usr/bin/env bash
# Generate FullPersons with DeepSeek for the same person descriptions used in
# electronics benchmark, then run XOR to compare welfare vs Mistral FullPersons.
#
# Usage (from DT Study directory):
#   nohup bash scripts/run-deepseek-fp-comparison.sh > logs/deepseek-fp-comparison.log 2>&1 &
#   tail -f logs/deepseek-fp-comparison.log

cd "$(dirname "$0")/.."
mkdir -p logs

PYTHON="$(pwd)/venv/bin/python"
ENV=".env.deepseek"
BENCH="electronics-deepseek-fp"
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

START_TIME=$(date '+%Y-%m-%d %H:%M:%S')
log "=== DeepSeek FullPerson generation (same seeds, different model) ==="
log "    Benchmark  : $BENCH (9 people, 3 setups, 6 items)"
log "    Model      : deepseek-chat (DeepSeek-V3)"
log "    Comparison : Mistral FullPersons in data/electronics/ELECTRONICS/"
log "    Start      : $START_TIME"

log "--- Generating FullPersons with DeepSeek ---"
"$PYTHON" scripts/make-fullpersons.py --benchmark "$BENCH" --env-file "$ENV" \
    || { log "ERROR: FullPerson generation failed"; exit 1; }

log "--- Running XOR auction on DeepSeek FullPersons ---"
"$PYTHON" scripts/run-proxy-xor.py --benchmark "$BENCH" --env_path "$ENV" \
    || { log "ERROR: XOR run failed"; exit 1; }

log "--- Comparing XOR welfare: Mistral vs DeepSeek FullPersons ---"
"$PYTHON" - <<PYEOF
import csv, json, os, glob

# DeepSeek XOR results
ds_welfare = {}
for f in glob.glob("data/${BENCH}-logs/log_Proxy-XOR_*.csv"):
    for r in csv.DictReader(open(f)):
        ds_welfare[r["setup_index"]] = float(r["total_auction_value"])

# Mistral XOR results (existing)
ms_welfare = {}
for f in glob.glob("data/electronics-deepseek-logs/log_Proxy-XOR_*.csv"):
    for r in csv.DictReader(open(f)):
        ms_welfare[r["setup_index"]] = float(r["total_auction_value"])

print(f"\n{'Setup':<8} {'Mistral XOR':>14} {'DeepSeek XOR':>14} {'Diff':>10} {'Diff%':>8}")
print("-" * 58)
for si in sorted(set(ds_welfare) | set(ms_welfare)):
    ms = ms_welfare.get(si, 0)
    ds = ds_welfare.get(si, 0)
    diff = ds - ms
    pct = (diff / ms * 100) if ms else 0
    print(f"Setup {si}  {ms:>14.1f} {ds:>14.1f} {diff:>+10.1f} {pct:>+7.1f}%")

# Also compare individual bundle valuations for one person
print("\n--- Sample person valuation comparison (alicegarcia, setup 0) ---")
ms_fp = "data/electronics/ELECTRONICS/0/FullPerson-alicegarcia.json"
ds_fp = "data/${BENCH}/ELECTRONICS/0/FullPerson-alicegarcia.json"
if os.path.exists(ms_fp) and os.path.exists(ds_fp):
    ms_xor = json.loads(json.load(open(ms_fp))["xor_valuation"])
    ds_xor = json.loads(json.load(open(ds_fp))["xor_valuation"])
    ms_bids = {b["bundle"]: b["value"] for b in ms_xor["atomic_bids"]}
    ds_bids = {b["bundle"]: b["value"] for b in ds_xor["atomic_bids"]}
    import json as _json
    for bundle_str in list(ms_bids)[:8]:
        bun = _json.loads(bundle_str)
        qtys = bun.get("quantities", [])
        ms_v = ms_bids.get(bundle_str, "?")
        ds_v = ds_bids.get(bundle_str, "?")
        print(f"  {qtys}  Mistral={ms_v}  DeepSeek={ds_v}")
PYEOF

log "--- Token & Cost Summary ---"
"$PYTHON" - <<PYEOF
import csv, os

start = "$START_TIME"
csv_path = "logs/token-usage.csv"
if not os.path.exists(csv_path):
    print("No token-usage.csv found.")
else:
    rows = list(csv.DictReader(open(csv_path)))
    ds_rows = [r for r in rows if r.get("provider") == "deepseek" and r.get("timestamp", "") >= start]
    prompt = sum(int(r.get("prompt_tokens", 0) or 0) for r in ds_rows)
    output = sum(int(r.get("completion_tokens", 0) or 0) for r in ds_rows)
    cost   = sum(float(r.get("cost_usd", 0) or 0) for r in ds_rows)
    print(f"  API calls      : {len(ds_rows)}")
    print(f"  Prompt tokens  : {prompt:,}")
    print(f"  Output tokens  : {output:,}")
    print(f"  Estimated cost : \${cost:.4f} USD")
PYEOF

log "ALL DONE."
