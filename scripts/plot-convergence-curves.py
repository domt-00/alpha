#!/usr/bin/env python3
"""
Plot efficiency-vs-interactions convergence curves from existing proxy logs.

Every auction log already contains one row per ICA iteration (welfare and
avg_human_interactions at that point), even though only the last row is
normally used for the "final efficiency" number. This script reuses that
per-iteration data to build convergence curves in the same style as Huang et
al.'s Figure 2: for each proxy, efficiency is plotted as a function of the
number of person-proxy interactions, not just reported as a single endpoint.

Methodology (matches the pilot study in the preliminary report): for each
setup, and for each query point i = 1, 2, ..., max_interactions, take the
efficiency from the first iteration whose avg_human_interactions is >= i.
Average across setups to get one curve per proxy.

Usage:
    python scripts/plot-convergence-curves.py \\
        --logs_dir data/electronics-specs-mistral-v2-logs \\
        --proxies VD1,VD2,H,NVD,NVD-Restrict,NVD-Prune,NVD-SR,NVD-R \\
        --max_interactions 30 \\
        --output convergence_specs_mistral.png
"""

import argparse
import csv
import glob
import os

import matplotlib.pyplot as plt


def load_xor_optimal(logs_dir):
    xor_files = sorted(glob.glob(os.path.join(logs_dir, "log_Proxy-XOR_*.csv")))
    if not xor_files:
        return {}
    with open(xor_files[-1], newline="") as f:
        rows = list(csv.DictReader(f))
    xor_opt = {}
    for r in rows:
        try:
            xor_opt[r["setup_index"]] = float(r["total_auction_value"])
        except (KeyError, ValueError):
            pass
    return xor_opt


def load_proxy_rows(logs_dir, proxy_name, exclude_discount_sensitivity=True):
    """
    Find the most recent log file for a given Proxy name and return its rows.

    Some directories contain multiple runs of the same proxy (e.g. VD2 re-run
    3-5x for a discount/epsilon-sensitivity study). Those runs are a deliberate
    parameter sweep, not the "main" comparison run, and picking the most
    recent file by timestamp can silently grab one of them instead of the
    intended baseline. By default, files whose first row has a
    Proxy-discount other than the pipeline default (0.75) are excluded.
    """
    pattern = os.path.join(logs_dir, f"log_Proxy-{proxy_name}_*.csv")
    files = sorted(f for f in glob.glob(pattern) if "routing" not in f)
    if not files:
        return None

    if exclude_discount_sensitivity:
        filtered = []
        for f in files:
            with open(f, newline="") as fh:
                first_row = next(csv.DictReader(fh), None)
            discount = first_row.get("Proxy-discount") if first_row else None
            if discount in (None, "", "0.75"):
                filtered.append(f)
        if filtered:
            files = filtered

    with open(files[-1], newline="") as f:
        return list(csv.DictReader(f))


def build_curve(rows, xor_opt, max_interactions):
    """
    For each setup, walk its rows (one per ICA iteration, in order) and record
    (avg_human_interactions, efficiency) at each point. Then for i = 1..max,
    take the efficiency at the first iteration with avg_interactions >= i.
    Average across setups for each i.
    """
    by_setup = {}
    for r in rows:
        si = r.get("setup_index", "0")
        try:
            interactions = float(r["avg_human_interactions"])
            welfare = float(r["total_auction_value"])
        except (KeyError, ValueError, TypeError):
            continue
        opt = xor_opt.get(si)
        if not opt:
            continue
        eff = 100 * welfare / opt
        by_setup.setdefault(si, []).append((interactions, eff))

    xs = list(range(1, max_interactions + 1))
    ys = []
    for i in xs:
        vals = []
        for si, series in by_setup.items():
            series_sorted = sorted(series, key=lambda t: t[0])
            match = next((eff for interactions, eff in series_sorted if interactions >= i), None)
            if match is None and series_sorted:
                match = series_sorted[-1][1]  # last known value if never reaches i
            if match is not None:
                vals.append(match)
        ys.append(sum(vals) / len(vals) if vals else None)
    return xs, ys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--logs_dir", required=True)
    parser.add_argument("--proxies", required=True, help="Comma-separated proxy names, e.g. VD1,VD2,NVD")
    parser.add_argument("--max_interactions", type=int, default=30)
    parser.add_argument("--output", required=True)
    parser.add_argument("--title", default=None)
    args = parser.parse_args()

    xor_opt = load_xor_optimal(args.logs_dir)
    if not xor_opt:
        print("[WARN] No XOR baseline found — efficiency cannot be computed.")
        return

    proxies = [p.strip() for p in args.proxies.split(",")]

    plt.figure(figsize=(9, 6))
    any_plotted = False
    for proxy in proxies:
        rows = load_proxy_rows(args.logs_dir, proxy)
        if not rows:
            print(f"[WARN] No log found for proxy={proxy}, skipping.")
            continue
        xs, ys = build_curve(rows, xor_opt, args.max_interactions)
        xs_clean = [x for x, y in zip(xs, ys) if y is not None]
        ys_clean = [y for y in ys if y is not None]
        if not ys_clean:
            print(f"[WARN] No usable data for proxy={proxy}, skipping.")
            continue
        plt.plot(xs_clean, ys_clean, marker="o", markersize=3, label=proxy)
        any_plotted = True

    if not any_plotted:
        print("[ERROR] Nothing to plot.")
        return

    plt.axhline(100, color="gray", linestyle="--", linewidth=1, alpha=0.6)
    plt.xlabel("Average person-proxy interactions")
    plt.ylabel("Allocative efficiency (%)")
    plt.title(args.title or f"Convergence — {os.path.basename(args.logs_dir)}")
    plt.legend()
    plt.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(args.output, dpi=150)
    print(f"[INFO] Saved to {args.output}")


if __name__ == "__main__":
    main()
