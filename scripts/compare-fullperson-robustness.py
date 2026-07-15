#!/usr/bin/env python3
"""
Compare bundle valuations across multiple FullPerson regenerations for the
same seed, to check (a) same-model repeated-generation consistency and
(b) cross-model consistency — extending Huang et al.'s Section 6.3/6.4
robustness checks from single-bundle repeated queries to whole-table
regeneration.

Usage:
    python scripts/compare-fullperson-robustness.py \\
        --files data/robustness-fullperson-alicegarcia/deepseek/rep1/FullPerson-alicegarcia.json:deepseek-rep1 \\
                data/robustness-fullperson-alicegarcia/deepseek/rep2/FullPerson-alicegarcia.json:deepseek-rep2 \\
                data/robustness-fullperson-alicegarcia/deepseek/rep3/FullPerson-alicegarcia.json:deepseek-rep3 \\
                data/robustness-fullperson-alicegarcia/mistral/rep1/FullPerson-alicegarcia.json:mistral-rep1 \\
                data/electronics/ELECTRONICS/0/FullPerson-alicegarcia.json:original-benchmark
"""

import argparse
import json
import statistics

from alpha.persons.full_person import FullPerson


def load_bundle_values(path):
    with open(path) as f:
        fp = FullPerson.from_json(f.read())
    return {str(bundle): value for bundle, value in fp.XOR_Valuation.atomic_bids}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--files", nargs="+", required=True,
                        help="List of path:label pairs.")
    args = parser.parse_args()

    labeled_values = {}
    for entry in args.files:
        path, label = entry.rsplit(":", 1)
        labeled_values[label] = load_bundle_values(path)
        print(f"[INFO] Loaded {label}: {len(labeled_values[label])} bundles from {path}")

    all_bundle_keys = set()
    for vals in labeled_values.values():
        all_bundle_keys.update(vals.keys())

    labels = list(labeled_values.keys())
    print(f"\n{'Bundle':<20}" + "".join(f"{l:>16}" for l in labels))
    for bkey in sorted(all_bundle_keys, key=lambda k: sum(int(x) for x in k.split(";"))):
        row = f"{bkey:<20}"
        for l in labels:
            v = labeled_values[l].get(bkey)
            row += f"{v if v is not None else '-':>16}"
        print(row)

    # Same-model consistency (any labels sharing a common prefix before '-rep' are grouped)
    print("\n=== Per-bundle statistics across all listed reps ===")
    total_abs_pct_diffs = []
    for bkey in sorted(all_bundle_keys, key=lambda k: sum(int(x) for x in k.split(";"))):
        vals = [labeled_values[l][bkey] for l in labels if bkey in labeled_values[l]]
        if len(vals) < 2:
            continue
        mean = statistics.mean(vals)
        std = statistics.pstdev(vals)
        cv = (std / mean * 100) if mean else 0
        print(f"  {bkey:<20} mean={mean:8.1f}  std={std:7.1f}  CV={cv:5.1f}%  values={vals}")
        if mean:
            total_abs_pct_diffs.append(std / mean * 100)

    if total_abs_pct_diffs:
        print(f"\nAverage per-bundle CV across all bundles: {statistics.mean(total_abs_pct_diffs):.1f}%")

    # Whole-table summary: total value (sum of all bundle values) per source — a rough
    # proxy for "how much does the overall valuation profile shift"
    print("\n=== Whole-table summary ===")
    for l in labels:
        total = sum(labeled_values[l].values())
        print(f"  {l:<20} sum_of_all_bundle_values={total:.0f}  n_bundles={len(labeled_values[l])}")


if __name__ == "__main__":
    main()
