#!/usr/bin/env python3
"""
NVD-SR (self-routing) proxy runner.
Identical to run-proxy-nvd.py but uses CECA_QLLM_A_SR_Proxy_Factory,
which skips opening questions when the LLM already has sufficient context.

Extra columns in output CSV:
  questions_asked   — how many questions were actually asked per person
  questions_skipped — how many were skipped by self-routing
"""

import os
import pandas as pd
from datetime import datetime
import argparse
import concurrent.futures

from dotenv import load_dotenv

from alpha.auctions.ceca import CECA_XOR
from alpha.auctions.ceca_qllm_a_sr import CECA_QLLM_A_SR_Proxy_Factory
from alpha.persons.full_person import FullPerson
from alpha.scenario import scenarios
from alpha.util import get_llm_model, get_llm_provider, setup_logging, token_tracker


def get_scenario_by_code(code):
    for s in scenarios:
        if s.code == code:
            return s
    return None


def discover_scenarios_and_setups(benchmark):
    base_dir = os.path.join("data", benchmark)
    if not os.path.isdir(base_dir):
        print(f"[ERROR] Benchmark directory does not exist: {base_dir}")
        return []
    scenario_dirs = [d for d in os.listdir(base_dir) if os.path.isdir(os.path.join(base_dir, d))]
    tasks = []
    for scenario_code in scenario_dirs:
        scenario_path = os.path.join(base_dir, scenario_code)
        for setup_index in os.listdir(scenario_path):
            if os.path.isdir(os.path.join(scenario_path, setup_index)):
                tasks.append((scenario_code, setup_index))
    return tasks


def process_scenario(benchmark, scenario_code, setup_index, proxy_factory, timestamp, max_iterations=None):
    directory = os.path.join("data", benchmark, scenario_code, str(setup_index))
    scenario_obj = get_scenario_by_code(scenario_code)
    if not scenario_obj:
        print(f"[WARN] No scenario object found for code={scenario_code}. Skipping.")
        return None, None

    print(f"[INFO] Processing scenario={scenario_code}, setup={setup_index} from {directory}")

    try:
        fullperson_files = [f for f in os.listdir(directory) if f.startswith("FullPerson") and f.endswith(".json")]
        if not fullperson_files:
            print(f"[WARN] No FullPerson JSON files found in {directory}. Skipping.")
            return None, None

        persons = []
        for fp_file in fullperson_files:
            with open(os.path.join(directory, fp_file)) as f:
                p = FullPerson.from_json(f.read())
                p.demand_mode = "RAND"
                persons.append(p)

        proxies = [proxy_factory(person) for person in persons]
        auction = CECA_XOR(max_iterations=max_iterations)
        print(f"[INFO] Running auction for scenario={scenario_code}, setup={setup_index} with {len(persons)} persons.")
        allocation = auction(scenario=scenario_obj, agents=proxies, persons=persons)

        values = []
        for proxy_allocation, proxy in zip(allocation, proxies):
            bundle, payment = proxy_allocation
            if bundle.total_quantity() == 0:
                continue
            value = proxy.RealPerson().Message("value", {"bundle": bundle})
            values.append(value)

        row = {
            "scenario": scenario_code,
            "setup_index": setup_index,
            "auction_values": values,
            "total_auction_value": sum(values),
            "human_interactions": [proxy.NumberOfHumanInteractions() for proxy in proxies],
            "avg_human_interactions": (
                sum(proxy.NumberOfHumanInteractions() for proxy in proxies) / len(proxies) if proxies else 0
            ),
            "questions_asked":   [getattr(proxy, "questions_asked",   0) for proxy in proxies],
            "questions_skipped": [getattr(proxy, "questions_skipped", 0) for proxy in proxies],
            "total_questions_asked":   sum(getattr(p, "questions_asked",   0) for p in proxies),
            "total_questions_skipped": sum(getattr(p, "questions_skipped", 0) for p in proxies),
        }

        log_df = pd.DataFrame(auction.log_rows)
        log_df["scenario"]   = scenario_code
        log_df["setup_index"] = setup_index

        return row, log_df

    except Exception as e:
        print(f"Error processing scenario={scenario_code}, setup={setup_index}: {e}")
        return None, None


def _init_worker(env_path):
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=env_path, override=True)


def main():
    setup_logging()

    parser = argparse.ArgumentParser(description="Run NVD-SR (self-routing) auction proxy.")
    parser.add_argument("--env_path",   type=str, default=".env")
    parser.add_argument("--benchmark",  type=str, required=True)
    parser.add_argument("--num_questions", type=int, required=True)
    parser.add_argument("--cap",           type=int, required=True)
    parser.add_argument("--min_iterations",type=int, required=True)
    parser.add_argument("--check_priority",         type=str, required=True)
    parser.add_argument("--target_bundle_priority", type=str, required=True)
    parser.add_argument("--happy_priority",         type=str, required=True)
    parser.add_argument("--target_bundle_emphasis", type=str, required=True)
    parser.add_argument("--anchor_num_target_bundles", type=str, required=True)
    parser.add_argument("--max_iterations", type=int, default=None)
    parser.add_argument("--compress_description", action="store_true", default=False,
                        help="Compress person description to compact WTP profile (saves ~75%% tokens).")

    args = parser.parse_args()
    token_tracker.set_context(benchmark=args.benchmark, stage="PROXY-NVD-SR")

    load_dotenv(dotenv_path=args.env_path)
    print(f"[INFO] Loaded environment variables from {args.env_path}")

    timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
    overall_log_df = pd.DataFrame()
    rows = []

    def make_factory():
        return CECA_QLLM_A_SR_Proxy_Factory(
            check_priority=args.check_priority,
            target_bundle_priority=args.target_bundle_priority,
            happy_priority=args.happy_priority,
            target_bundle_emphasis=args.target_bundle_emphasis,
            anchor_num_target_bundles=args.anchor_num_target_bundles,
            num_questions=args.num_questions,
            cap=args.cap,
            min_iterations=args.min_iterations,
            compress_description=args.compress_description,
        )

    tasks = discover_scenarios_and_setups(args.benchmark)
    if not tasks:
        print("[WARN] No scenarios or setups discovered. Exiting.")
        return

    print(f"[INFO] Discovered {len(tasks)} scenario+setup tasks to run.")

    max_workers = min(12, len(tasks))
    with concurrent.futures.ProcessPoolExecutor(max_workers=max_workers, initializer=_init_worker, initargs=(args.env_path,)) as executor:
        futures = [
            executor.submit(process_scenario, args.benchmark, sc, si, make_factory(), timestamp, args.max_iterations)
            for sc, si in tasks
        ]
        for future in concurrent.futures.as_completed(futures):
            row, log_df = future.result()
            if row is not None and log_df is not None:
                rows.append(row)
                overall_log_df = pd.concat([overall_log_df, log_df], ignore_index=True)

    overall_log_df["Proxy"] = "Proxy-NVD-SR"
    overall_log_df["Proxy-check_priority"]          = args.check_priority
    overall_log_df["Proxy-target_bundle_priority"]  = args.target_bundle_priority
    overall_log_df["Proxy-happy_priority"]          = args.happy_priority
    overall_log_df["Proxy-target_bundle_emphasis"]  = args.target_bundle_emphasis
    overall_log_df["Proxy-anchor_num_target_bundles"] = args.anchor_num_target_bundles
    overall_log_df["Person"]    = "FullPerson"
    overall_log_df["Timestamp"] = timestamp
    overall_log_df["Provider"] = get_llm_provider()
    overall_log_df["Model"] = get_llm_model()

    out_dir = f"data/{args.benchmark}-logs"
    os.makedirs(out_dir, exist_ok=True)
    log_filename = os.path.join(out_dir, f"log_Proxy-NVD-SR_{timestamp}.csv")
    overall_log_df.to_csv(log_filename, index=False)
    print(f"[INFO] Processing complete. Logs saved to {log_filename}")

    # Write per-setup SR routing summary to a separate CSV
    if rows:
        sr_df = pd.DataFrame(rows)
        sr_filename = os.path.join(out_dir, f"log_Proxy-NVD-SR-routing_{timestamp}.csv")
        sr_df.to_csv(sr_filename, index=False)
        print(f"[INFO] SR routing stats saved to {sr_filename}")

        total_asked   = sum(r["total_questions_asked"]   for r in rows)
        total_skipped = sum(r["total_questions_skipped"] for r in rows)
        total = total_asked + total_skipped
        print(f"\n[SR] Questions asked  : {total_asked} / {total} ({100*total_asked/total:.1f}%)")
        print(f"[SR] Questions skipped: {total_skipped} / {total} ({100*total_skipped/total:.1f}%)")


if __name__ == "__main__":
    main()
