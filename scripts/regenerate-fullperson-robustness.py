#!/usr/bin/env python3
"""
Regenerate a FullPerson's valuation table from an EXISTING seed, to test
whether re-running FullPerson generation for an unchanged seed produces a
consistent XOR valuation table.

Neither of the two robustness checks in Huang et al. (2025) test this
directly: Section 6.3 compares valuations across different *models* for the
same seed (cross-model robustness), and Section 6.4 re-queries a *single*
bundle value 10 times along an add/remove-items path (per-bundle repeated-
call variance). Neither regenerates the *entire* 2^N-bundle table from
scratch and compares the resulting tables against each other.

This script loads an existing seed (kept fixed), constructs a fresh
FullPerson (forcing full LLM-based regeneration of every bundle's value —
NOT loading the cached given_valuation), and saves the result to a clearly
labeled, traceable path: <output_dir>/<model>/rep<N>/FullPerson-<name>.json

Usage:
    python scripts/regenerate-fullperson-robustness.py \\
        --seed_path data/electronics/ELECTRONICS/0/alicegarcia.json \\
        --scenario_code ELECTRONICS \\
        --env_path .env.deepseek \\
        --model_label deepseek \\
        --rep 1 \\
        --output_dir data/robustness-fullperson-alicegarcia
"""

import argparse
import json
import os

from dotenv import load_dotenv

from alpha.person import Seed
from alpha.persons.full_person import FullPerson
from alpha.scenario import scenarios


def get_scenario_by_code(code):
    for s in scenarios:
        if s.code == code:
            return s
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed_path", required=True, help="Path to an existing seed JSON file (kept unchanged).")
    parser.add_argument("--scenario_code", required=True)
    parser.add_argument("--env_path", default=".env")
    parser.add_argument("--model_label", required=True, help="Label for the output folder, e.g. 'deepseek' or 'mistral'.")
    parser.add_argument("--rep", type=int, required=True, help="Repetition number, e.g. 1, 2, 3.")
    parser.add_argument("--output_dir", required=True)
    args = parser.parse_args()

    load_dotenv(dotenv_path=args.env_path)

    scenario = get_scenario_by_code(args.scenario_code)
    if not scenario:
        print(f"[ERROR] Scenario not found: {args.scenario_code}")
        return

    with open(args.seed_path) as f:
        seed_data = f.read()
    seed = Seed.from_json(seed_data)

    print(f"[INFO] Regenerating FullPerson for seed={seed.code} model={args.model_label} rep={args.rep}")
    print(f"[INFO] This makes one LLM call per possible bundle (2^{len(scenario)} - 1 bundles).")

    # Constructing without given_valuation forces full regeneration via LLM calls.
    fp = FullPerson(scenario, seed)

    out_dir = os.path.join(args.output_dir, args.model_label, f"rep{args.rep}")
    os.makedirs(out_dir, exist_ok=True)

    seed_out_path = os.path.join(out_dir, f"{seed.code}.json")
    with open(seed_out_path, "w") as f:
        json.dump(json.loads(seed.to_json()), f)

    fp_out_path = os.path.join(out_dir, f"FullPerson-{seed.code}.json")
    with open(fp_out_path, "w") as f:
        json.dump(json.loads(fp.to_json()), f)

    print(f"[INFO] Saved to {fp_out_path}")


if __name__ == "__main__":
    main()
