"""
test-prompt-size.py
-------------------
Investigates how the amount of information in a bidder description
affects the quality of LLM-generated bundle valuations.

Three prompt variants for the same bidder (Diana):
  SHORT  : one sentence — minimal context
  MEDIUM : one structured paragraph — key preferences + values
  FULL   : the complete 4-step generated description (~1,800 tokens)

Runs 10 representative bundles for each variant and compares:
  - The dollar values produced
  - Agreement between variants
  - Approximate token cost

Usage:
    cd "DT Study"
    source venv/bin/activate
    python scripts/test-prompt-size.py
"""

import json
import statistics
import os
import csv
from dotenv import load_dotenv

load_dotenv(".env")

from alpha.scenario import TransportationScenario as scenario, Bundle
from alpha.person import Seed
from alpha.persons.standard_person.core import StandardValuePipeline

# ── Load Diana's full description from disk ───────────────────────────────────

with open("data/first/TRANSPORTATION/0/dianaanderson.json") as f:
    full_desc = json.load(f)["description"]

# ── Define three prompt variants ──────────────────────────────────────────────

SHORT = (
    "Diana is a budget-conscious parent in her mid-40s who wants a comfortable, "
    "practical city bike for running errands. Her budget is around $700."
)

MEDIUM = (
    "Diana is a budget-conscious parent in her mid-40s looking for a practical "
    "city bike for running errands and chauffeuring her kids. "
    "She values the Schwinn Suburban (SCHWIN) at $700 — her top choice for its "
    "comfort and rear rack. Her secondary option is the Titan Escape 3 (TITAN) "
    "at $550. She rejects all electric scooters (ESCOOT1, ESCOOT2, VOLTRON) "
    "entirely due to safety concerns, valuing them at $0. She also has no interest "
    "in the Troik Verve+ 2 (TROIK) hybrid bike ($0 — unnecessary for her needs). "
    "She only ever wants one item: if a bundle contains multiple items, she values "
    "it at the price of her preferred item within it and ignores the rest. "
    "She would not pay more for a bundle than for her top item alone."
)

FULL = full_desc

VARIANTS = {
    "SHORT  ": SHORT,
    "MEDIUM ": MEDIUM,
    "FULL   ": FULL,
}

# ── Representative bundles ────────────────────────────────────────────────────
# Covers: all 6 singletons + 4 meaningful combinations

TEST_BUNDLES = [
    Bundle(scenario, [0, 0, 0, 0, 0, 1]),  # SCHWIN only          ← Diana's top pick
    Bundle(scenario, [0, 0, 0, 0, 1, 0]),  # TITAN only           ← secondary
    Bundle(scenario, [0, 0, 0, 1, 0, 0]),  # TROIK only           ← rejected
    Bundle(scenario, [1, 0, 0, 0, 0, 0]),  # ESCOOT1 only         ← rejected (scooter)
    Bundle(scenario, [0, 1, 0, 0, 0, 0]),  # ESCOOT2 only         ← rejected (scooter)
    Bundle(scenario, [0, 0, 1, 0, 0, 0]),  # VOLTRON only         ← rejected (scooter)
    Bundle(scenario, [0, 0, 0, 0, 1, 1]),  # TITAN + SCHWIN       ← both bikes she likes
    Bundle(scenario, [0, 0, 0, 1, 0, 1]),  # TROIK + SCHWIN       ← wanted + unwanted
    Bundle(scenario, [1, 0, 0, 0, 0, 1]),  # ESCOOT1 + SCHWIN     ← scooter + her top bike
    Bundle(scenario, [1, 1, 1, 1, 1, 1]),  # ALL items            ← grand bundle
]

BUNDLE_LABELS = [
    "SCHWIN only",
    "TITAN only",
    "TROIK only",
    "ESCOOT1 only",
    "ESCOOT2 only",
    "VOLTRON only",
    "TITAN + SCHWIN",
    "TROIK + SCHWIN",
    "ESCOOT1 + SCHWIN",
    "ALL items",
]

# ── Run valuations ────────────────────────────────────────────────────────────

pipeline = StandardValuePipeline()
results = {}  # variant_name → list of values

print("=" * 65)
print("  Prompt Size Experiment — Diana Anderson")
print("  Scenario: TRANSPORTATION (6 items)")
print(f"  Bundles tested: {len(TEST_BUNDLES)}")
print("=" * 65)

for variant_name, description in VARIANTS.items():
    print(f"\n{'─'*65}")
    print(f"  Variant: {variant_name.strip()}")
    print(f"  Description length: ~{len(description)//4} tokens")
    print(f"{'─'*65}")

    # Create a temporary Seed with this variant's description
    seed = Seed(code="dianaanderson", scenario="TRANSPORTATION", description=description)

    values = []
    for bundle, label in zip(TEST_BUNDLES, BUNDLE_LABELS):
        try:
            value = pipeline(scenario=scenario, seed=seed, bundle=bundle)
            values.append(value)
            print(f"  {label:<25} → ${value:,.0f}")
        except Exception as e:
            values.append(None)
            print(f"  {label:<25} → ERROR: {e}")

    results[variant_name.strip()] = values

# ── Side-by-side comparison ───────────────────────────────────────────────────

print(f"\n{'='*85}")
print("  SIDE-BY-SIDE COMPARISON")
print(f"{'='*85}")
print(f"  {'Bundle':<25} {'SHORT':>10} {'MEDIUM':>10} {'FULL':>10} {'SHORT vs FULL':>15} {'MED vs FULL':>13}")
print(f"  {'-'*25} {'-'*10} {'-'*10} {'-'*10} {'-'*15} {'-'*13}")

short_vals  = results.get("SHORT",  [None]*len(TEST_BUNDLES))
medium_vals = results.get("MEDIUM", [None]*len(TEST_BUNDLES))
full_vals   = results.get("FULL",   [None]*len(TEST_BUNDLES))

short_diffs  = []
medium_diffs = []

for label, s, m, f in zip(BUNDLE_LABELS, short_vals, medium_vals, full_vals):
    s_str = f"${s:,.0f}" if s is not None else "ERR"
    m_str = f"${m:,.0f}" if m is not None else "ERR"
    f_str = f"${f:,.0f}" if f is not None else "ERR"

    if s is not None and f is not None and f != 0:
        sd = abs(s - f) / f * 100
        short_diffs.append(sd)
        sd_str = f"{sd:.1f}%"
    elif s is not None and f is not None and f == 0:
        sd = 0.0 if s == 0 else 100.0
        short_diffs.append(sd)
        sd_str = f"{sd:.1f}%"
    else:
        sd_str = "N/A"

    if m is not None and f is not None and f != 0:
        md = abs(m - f) / f * 100
        medium_diffs.append(md)
        md_str = f"{md:.1f}%"
    elif m is not None and f is not None and f == 0:
        md = 0.0 if m == 0 else 100.0
        medium_diffs.append(md)
        md_str = f"{md:.1f}%"
    else:
        md_str = "N/A"

    print(f"  {label:<25} {s_str:>10} {m_str:>10} {f_str:>10} {sd_str:>15} {md_str:>13}")

print(f"  {'-'*25} {'-'*10} {'-'*10} {'-'*10} {'-'*15} {'-'*13}")

if short_diffs:
    print(f"\n  SHORT  vs FULL — Mean diff: {statistics.mean(short_diffs):.1f}%   Max: {max(short_diffs):.1f}%")
if medium_diffs:
    print(f"  MEDIUM vs FULL — Mean diff: {statistics.mean(medium_diffs):.1f}%   Max: {max(medium_diffs):.1f}%")

# ── Token cost summary ────────────────────────────────────────────────────────

print(f"\n{'='*65}")
print("  TOKEN COST ESTIMATE (for full 64-bundle XOR table)")
print(f"{'='*65}")

for name, desc in VARIANTS.items():
    desc_tokens = len(desc) // 4
    total_input  = (desc_tokens + 50) * 64   # desc + bundle description per call
    total_output = 50 * 64                    # short answer per call
    total = total_input + total_output
    print(f"  {name.strip():<8}: ~{desc_tokens:>5} tokens/call × 64 = ~{total:>7,} tokens total")

# ── Save to CSV ───────────────────────────────────────────────────────────────

os.makedirs("data/experiments", exist_ok=True)
csv_path = "data/experiments/prompt_size_results.csv"

with open(csv_path, "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["bundle", "short", "medium", "full",
                     "short_vs_full_pct", "medium_vs_full_pct"])
    for i, label in enumerate(BUNDLE_LABELS):
        s = short_vals[i]
        m = medium_vals[i]
        fv = full_vals[i]

        def diff(a, b):
            if a is None or b is None:
                return ""
            if b == 0:
                return 0.0 if a == 0 else 100.0
            return round(abs(a - b) / b * 100, 1)

        writer.writerow([label, s, m, fv, diff(s, fv), diff(m, fv)])

print(f"\n  Results saved to {csv_path}")
print()
