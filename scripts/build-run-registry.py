#!/usr/bin/env python3
"""
Build a master registry of every experiment run across all benchmarks.

Scans all data/*-logs/ directories, reads every proxy log CSV, and
produces logs/run-registry.csv — one row per run with key metadata.

Usage:
    python scripts/build-run-registry.py
    python scripts/build-run-registry.py --print   # also print summary table
"""

import os
import csv
import glob
import argparse
from datetime import datetime


PROXY_ORDER = ["Proxy-XOR", "Proxy-VD1", "Proxy-VD2", "Proxy-H",
               "Proxy-NVD", "Proxy-NVD-SR", "Proxy-NVD-Restrict",
               "Proxy-NVD-Prune", "Proxy-NVD-R"]


def parse_timestamp(ts_str):
    """Parse yyyymmddHHMMSSffffff timestamp string."""
    try:
        return datetime.strptime(ts_str[:14], "%Y%m%d%H%M%S").strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return ts_str


def read_log(filepath):
    """Read a proxy log CSV and extract summary metadata."""
    try:
        with open(filepath, newline="") as f:
            rows = list(csv.DictReader(f))
    except Exception:
        return None
    if not rows:
        return None

    # Aggregate across setups
    setup_welfare = {}
    setup_interactions = {}
    for r in rows:
        si = r.get("setup_index", "0")
        try:
            setup_welfare[si] = float(r["total_auction_value"])
        except (KeyError, ValueError):
            pass
        try:
            setup_interactions[si] = float(r.get("avg_human_interactions") or 0)
        except (KeyError, ValueError):
            pass

    total_welfare    = sum(setup_welfare.values())
    avg_interactions = (sum(setup_interactions.values()) / len(setup_interactions)
                        if setup_interactions else None)
    n_setups = len(setup_welfare)

    first = rows[0]
    return {
        "proxy":               first.get("Proxy", ""),
        "scenario":            first.get("scenario", ""),
        "provider":            first.get("Provider", "unknown"),
        "model":               first.get("Model", "unknown"),
        "compress_description": first.get("CompressDescription", ""),
        "num_setups":          n_setups,
        "total_welfare":       total_welfare,
        "avg_interactions":    avg_interactions,
        "timestamp_raw":       first.get("Timestamp", ""),
        "timestamp":           parse_timestamp(first.get("Timestamp", "")),
        "check_priority":      first.get("Proxy-check_priority", ""),
        "target_priority":     first.get("Proxy-target_bundle_priority", ""),
        "happy_priority":      first.get("Proxy-happy_priority", ""),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--print", action="store_true", help="Print summary table to stdout")
    args = parser.parse_args()

    base = os.path.join(os.path.dirname(__file__), "..")
    log_dirs = sorted(glob.glob(os.path.join(base, "data", "*-logs")))

    records = []

    for log_dir in log_dirs:
        benchmark = os.path.basename(log_dir).replace("-logs", "")
        csv_files = sorted(glob.glob(os.path.join(log_dir, "log_Proxy-*.csv")))

        # Find XOR welfare per setup for this benchmark (use most recent XOR log)
        xor_files = sorted(glob.glob(os.path.join(log_dir, "log_Proxy-XOR_*.csv")))
        xor_welfare_by_setup = {}
        if xor_files:
            try:
                with open(xor_files[-1], newline="") as f:
                    for r in csv.DictReader(f):
                        si = r.get("setup_index", "0")
                        try:
                            xor_welfare_by_setup[si] = float(r["total_auction_value"])
                        except (KeyError, ValueError):
                            pass
            except Exception:
                pass
        xor_total = sum(xor_welfare_by_setup.values()) or None

        for filepath in csv_files:
            filename = os.path.basename(filepath)
            # Skip routing files (not auction results)
            if "routing" in filename.lower():
                continue

            meta = read_log(filepath)
            if meta is None:
                continue

            efficiency = None
            if xor_total and meta["total_welfare"] is not None:
                efficiency = meta["total_welfare"] / xor_total * 100

            records.append({
                "benchmark":           benchmark,
                "proxy":               meta["proxy"],
                "provider":            meta["provider"],
                "model":               meta["model"],
                "compress_description": meta["compress_description"],
                "timestamp":           meta["timestamp"],
                "num_setups":          meta["num_setups"],
                "total_welfare":       round(meta["total_welfare"], 1) if meta["total_welfare"] is not None else "",
                "xor_optimal":         round(xor_total, 1) if xor_total else "",
                "efficiency_pct":      round(efficiency, 1) if efficiency is not None else "",
                "avg_interactions":    round(meta["avg_interactions"], 2) if meta["avg_interactions"] is not None else "",
                "check_priority":      meta["check_priority"],
                "target_priority":     meta["target_priority"],
                "happy_priority":      meta["happy_priority"],
                "filename":            filename,
            })

    # Sort by benchmark, proxy order, then timestamp
    proxy_rank = {p: i for i, p in enumerate(PROXY_ORDER)}
    records.sort(key=lambda r: (
        r["benchmark"],
        proxy_rank.get(r["proxy"], 99),
        r["timestamp"],
    ))

    # Write registry
    out_path = os.path.join(base, "logs", "run-registry.csv")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    fieldnames = ["benchmark", "proxy", "provider", "model", "compress_description",
                  "timestamp", "num_setups", "total_welfare", "xor_optimal",
                  "efficiency_pct", "avg_interactions", "check_priority",
                  "target_priority", "happy_priority", "filename"]

    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)

    print(f"[OK] Registry written: {out_path}  ({len(records)} runs)")

    if args.print:
        # Print a condensed summary table
        print()
        benchmarks = sorted(set(r["benchmark"] for r in records))
        for bench in benchmarks:
            bench_rows = [r for r in records if r["benchmark"] == bench]
            print(f"\n{'=' * 72}")
            print(f"  {bench}")
            print(f"{'=' * 72}")
            print(f"  {'Proxy':<18} {'Model':<22} {'Welfare':>8} {'Eff%':>6} {'AvgInt':>7}  {'Date'}")
            print(f"  {'-' * 68}")
            for r in bench_rows:
                model_str = f"{r['provider']}/{r['model']}"[:21]
                compress  = " [C]" if str(r.get("compress_description", "")).lower() == "true" else ""
                eff       = f"{r['efficiency_pct']}%" if r["efficiency_pct"] != "" else "N/A"
                print(f"  {r['proxy'] + compress:<18} {model_str:<22} "
                      f"{str(r['total_welfare']):>8} {eff:>6} "
                      f"{str(r['avg_interactions']):>7}  {r['timestamp'][:10]}")


if __name__ == "__main__":
    main()
