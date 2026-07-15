"""
test-batch-valuation.py
-----------------------
Compares two approaches for computing bundle valuations:

  A) ORIGINAL: one LLM call per bundle (64 calls per person)
  B) BATCHED:  one LLM call for ALL bundles at once

Runs both on the same seed and a representative subset of bundles,
then prints a side-by-side comparison.

Usage:
    cd "DT Study"
    python scripts/test-batch-valuation.py
"""

import json
import itertools
import statistics
import os
from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv(".env")

from alpha.scenario import Scenario, Bundle
from alpha.person import Seed
from alpha.persons.standard_person.core import StandardValuePipeline
from alpha.util import get_llm_client, get_llm_model, parse_structured_output

# ── Load an existing seed from disk ───────────────────────────────────────────

SEED_PATH = "data/first/TRANSPORTATION/0/dianaanderson.json"

with open(SEED_PATH) as f:
    raw = json.load(f)

seed = Seed.from_json(json.dumps(raw))

from alpha.scenario import TransportationScenario as scenario

print(f"Loaded seed: {seed.code}")
print(f"Scenario:    {scenario.code} ({len(scenario)} items)")
print()

# ── Pick a representative subset of bundles ───────────────────────────────────
# Testing all 64 would cost too many tokens for a comparison test.
# We pick 8 representative ones: empty, 6 singletons, 1 combo.

N = len(scenario)

test_bundles = [
    Bundle(scenario, [0, 0, 0, 0, 0, 1]),  # SCHWIN only
    Bundle(scenario, [0, 0, 0, 0, 1, 0]),  # TITAN only
    Bundle(scenario, [0, 0, 0, 1, 0, 0]),  # TROIK only
    Bundle(scenario, [1, 0, 0, 0, 0, 0]),  # ESCOOT1 only
    Bundle(scenario, [0, 1, 0, 0, 0, 0]),  # ESCOOT2 only
    Bundle(scenario, [0, 0, 1, 0, 0, 0]),  # VOLTRON only
    Bundle(scenario, [0, 0, 0, 0, 1, 1]),  # TITAN + SCHWIN
    Bundle(scenario, [0, 0, 0, 1, 0, 1]),  # TROIK + SCHWIN
]

print(f"Testing {len(test_bundles)} representative bundles.\n")

# ── APPROACH A: Individual queries (original method) ──────────────────────────

print("=" * 60)
print("APPROACH A — Individual query per bundle (original)")
print("=" * 60)

pipeline = StandardValuePipeline()
individual_values = {}

for bundle in test_bundles:
    desc = bundle.to_code_description()
    try:
        value = pipeline(scenario=scenario, seed=seed, bundle=bundle)
        individual_values[str(bundle)] = value
        print(f"  {desc:<40} → ${value:,.0f}")
    except Exception as e:
        individual_values[str(bundle)] = None
        print(f"  {desc:<40} → ERROR: {e}")

# ── APPROACH B: Batched — all bundles in one call ─────────────────────────────

print()
print("=" * 60)
print("APPROACH B — All bundles in single batched call")
print("=" * 60)

# Pydantic model for the batched response
class SingleBundleValue(BaseModel):
    bundle_index: int
    value: float

class BatchedBundleValues(BaseModel):
    values: list[SingleBundleValue]

# Build the prompt listing all bundles
bundle_lines = "\n".join([
    f"{i+1}. {b.to_code_description()}"
    for i, b in enumerate(test_bundles)
])

value_statement = """
Please use this process for each bundle:
  1. Check if the person has explicitly stated the value for that bundle
  2. Find the closest bundle the person has explicitly valued
  3. Identify the process by which the person calculates their value
  4. Factor in any other relevant criteria
  5. Estimate the person's value
"""

messages = [
    {
        "role": "user",
        "content": (
            f"Here is the scenario: {scenario}\n\n"
            f"Here is a bidder's preferences:\n\n{seed.description}\n\n"
            f"{value_statement}\n"
            f"Please value each of the following bundles for this bidder. "
            f"Return a JSON object with a list where each entry has "
            f"'bundle_index' (1-based) and 'value' (dollar amount as a number).\n\n"
            f"{bundle_lines}\n\n"
            f"Respond ONLY with JSON matching this schema:\n"
            f'{{"values": [{{"bundle_index": 1, "value": 700}}, ...]}}'
        )
    }
]

client = get_llm_client()
model = get_llm_model()

batched_values = {}

try:
    result = parse_structured_output(client, model, messages, BatchedBundleValues)
    for entry in result.values:
        idx = entry.bundle_index - 1  # convert to 0-based
        if 0 <= idx < len(test_bundles):
            bundle = test_bundles[idx]
            batched_values[str(bundle)] = entry.value
            desc = bundle.to_code_description()
            print(f"  {desc:<40} → ${entry.value:,.0f}")
except Exception as e:
    print(f"  ERROR: {e}")

# ── Side-by-side comparison ───────────────────────────────────────────────────

print()
print("=" * 60)
print("COMPARISON — Individual vs Batched")
print("=" * 60)
print(f"{'Bundle':<40} {'Individual':>12} {'Batched':>10} {'Diff':>10} {'Diff%':>8}")
print("-" * 84)

diffs = []
for bundle in test_bundles:
    key = str(bundle)
    desc = bundle.to_code_description()
    ind = individual_values.get(key)
    bat = batched_values.get(key)

    if ind is not None and bat is not None:
        diff = abs(ind - bat)
        diff_pct = (diff / ind * 100) if ind != 0 else 0
        diffs.append(diff_pct)
        print(f"  {desc:<38} ${ind:>10,.0f} ${bat:>8,.0f} ${diff:>8,.0f} {diff_pct:>7.1f}%")
    elif ind is None and bat is not None:
        print(f"  {desc:<38} {'ERROR':>11} ${bat:>8,.0f} {'N/A':>9} {'N/A':>8}")
    elif ind is not None and bat is None:
        print(f"  {desc:<38} ${ind:>10,.0f} {'ERROR':>9} {'N/A':>9} {'N/A':>8}")
    else:
        print(f"  {desc:<38} {'ERROR':>11} {'ERROR':>9} {'N/A':>9} {'N/A':>8}")

print("-" * 84)
if diffs:
    print(f"\n  Mean absolute difference: {statistics.mean(diffs):.1f}%")
    print(f"  Max  absolute difference: {max(diffs):.1f}%")
    print(f"  Bundles where values match exactly (0% diff): {sum(1 for d in diffs if d == 0)}/{len(diffs)}")

print()
print("=" * 60)
print("TOKEN COST ESTIMATE")
print("=" * 60)
n_bundles = 64  # full XOR table
print(f"  Original approach : {n_bundles} calls × ~2,000 tokens = ~{n_bundles * 2000:,} tokens per person")
print(f"  Batched approach  : 1 call   × ~4,000 tokens = ~4,000 tokens per person")
print(f"  Saving            : ~{(1 - 4000 / (n_bundles * 2000)) * 100:.0f}% reduction")
